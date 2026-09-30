"""Tests for user-auth: JWT login, re-issue on login, logout, Bearer enforcement."""
import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from tests.conftest import BearerClient, execute, query_one


def _session_count(db: dict) -> int:
    return query_one(db, "SELECT count(*) AS n FROM sessions")["n"]


def _login(client, username: str, password: str):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def _token_segments(token: str) -> list[str]:
    return token.split(".")


def _decode_payload(token: str) -> dict:
    payload_b64 = _token_segments(token)[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _make_expired_token(user_id: int, jti: str) -> str:
    """Craft a token with an expired exp, signed with the test secret."""
    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            "sub": str(user_id),
            "jti": jti,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


class TestLogin:
    def test_login_success_returns_jwt(self, flask_app, test_db):
        """Teacher with correct credentials gets a JWT in the body + DB row, no cookie."""
        client = flask_app.test_client()
        resp = _login(client, "teacher_a", "teacher_a_pass")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["role"] == "teacher"
        assert data["user"]["classId"] == 1

        token = data["token"]
        assert len(_token_segments(token)) == 3

        # No cookie-based session establishment
        assert "Set-Cookie" not in resp.headers

        # Payload holds sub/jti/iat/exp only — no role/class/password
        payload = _decode_payload(token)
        assert payload["sub"] == "1"
        assert set(payload.keys()) == {"sub", "jti", "iat", "exp"}
        assert "teacher" not in json.dumps(payload)
        assert "password" not in json.dumps(payload)

        # The jti is registered server-side with an expiry
        row = query_one(test_db, "SELECT id, user_id, expires_at FROM sessions")
        assert row["id"] == payload["jti"]
        assert row["user_id"] == 1
        assert _session_count(test_db) == 1

    def test_login_reissues_distinct_tokens(self, flask_app, test_db):
        """Two logins issue distinct tokens; both are valid (multi-device)."""
        client = flask_app.test_client()
        r1 = _login(client, "teacher_a", "teacher_a_pass")
        r2 = _login(client, "teacher_a", "teacher_a_pass")
        token1 = r1.get_json()["token"]
        token2 = r2.get_json()["token"]
        assert token1 != token2
        assert _session_count(test_db) == 2

        # Both tokens work (fresh clients carry one each)
        for token in (token1, token2):
            bearer = BearerClient(flask_app.test_client(), token)
            resp = bearer.get("/auth/me")
            assert resp.status_code == 200

    def test_login_wrong_password(self, app_client):
        """Wrong password → 401 with same error as non-existent user."""
        resp = _login(app_client, "teacher_a", "wrong_password")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid credentials"

    def test_login_nonexistent_user(self, app_client):
        """Non-existent user → same 401 as wrong password (no user existence leak)."""
        resp = _login(app_client, "ghost_user", "anything")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid credentials"


class TestAuthRequired:
    def test_unauth_api_returns_401_json(self, app_client):
        """API request without Authorization header → 401 JSON."""
        resp = app_client.get("/auth/me", headers={"Accept": "application/json"})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "unauthorized"

    def test_garbage_bearer_token_rejected(self, app_client):
        """Malformed Authorization header → 401."""
        resp = app_client.get(
            "/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert resp.status_code == 401

    def test_tampered_payload_rejected(self, flask_app, app_client):
        """Tampering with the payload breaks the signature → 401."""
        resp = _login(flask_app.test_client(), "teacher_a", "teacher_a_pass")
        token = resp.get_json()["token"]
        head, payload_b64, sig = _token_segments(token)
        real = _decode_payload(token)
        real["sub"] = "999"
        forged_b64 = base64.urlsafe_b64encode(json.dumps(real).encode()).rstrip(b"=")
        forged = f"{head}.{forged_b64.decode()}.{sig}"
        assert (
            app_client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code
            == 401
        )

    def test_expired_token_rejected(self, flask_app, app_client, test_db):
        """An expired exp is rejected even with a live sessions row."""
        from tests.conftest import execute as _exec

        _exec(
            test_db,
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
            ("expired-jti", 1, datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)),
        )
        token = _make_expired_token(1, "expired-jti")
        resp = app_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_identity_read_from_db_per_request(self, flask_app, test_db):
        """Role/class come from the users table per request, not a login snapshot."""
        client = flask_app.test_client()
        resp = _login(client, "student_a", "student_a_pass")
        bearer = BearerClient(client, resp.get_json()["token"])
        # Promote student_a to teacher directly in DB
        execute(test_db, "UPDATE users SET role = 'teacher' WHERE username = 'student_a'")
        resp = bearer.get("/auth/me")
        assert resp.status_code == 200
        assert resp.get_json()["user"]["role"] == "teacher"


class TestLogout:
    def test_logout_invalidates_session_immediately(self, flask_app, test_db):
        """Logout deletes the session row; the old token is dead right away."""
        client = flask_app.test_client()
        resp = _login(client, "student_a", "student_a_pass")
        token = resp.get_json()["token"]
        assert _session_count(test_db) == 1

        bearer = BearerClient(client, token)
        resp = bearer.post("/auth/logout")
        assert resp.status_code == 200
        assert _session_count(test_db) == 0

        # The very same token can no longer be used
        stale = flask_app.test_client()
        resp = stale.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


class TestNoPlaintextLogs:
    def test_login_failure_no_plaintext_in_logs(self, app_client, caplog):
        """Login failure logs must not contain the submitted password."""
        caplog.set_level(logging.DEBUG)
        app_client.post(
            "/auth/login",
            json={"username": "teacher_a", "password": "secret_pw_xyz"},
        )
        for record in caplog.records:
            assert "secret_pw_xyz" not in record.getMessage()

    def test_login_success_no_plaintext_in_logs(self, app_client, caplog):
        """Login success logs must not contain the submitted password."""
        caplog.set_level(logging.DEBUG)
        app_client.post(
            "/auth/login",
            json={"username": "teacher_a", "password": "teacher_a_pass"},
        )
        for record in caplog.records:
            assert "teacher_a_pass" not in record.getMessage()
