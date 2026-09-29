"""Tests for user-auth: session login, re-issue on login, logout, cookie flags."""
import logging

from tests.conftest import execute, query_one


def _session_count(db: dict) -> int:
    return query_one(db, "SELECT count(*) AS n FROM sessions")["n"]


class TestLogin:
    def test_login_success_sets_session(self, flask_app, test_db):
        """Teacher with correct credentials gets HttpOnly session cookie + DB row."""
        client = flask_app.test_client()
        resp = client.post(
            "/auth/login",
            json={"username": "teacher_a", "password": "teacher_a_pass"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["role"] == "teacher"
        assert data["user"]["classId"] == 1

        set_cookie = resp.headers.get("Set-Cookie", "")
        assert "HttpOnly" in set_cookie
        assert "SameSite=Lax" in set_cookie
        assert "session_id=" in set_cookie
        # Cookie must not carry role/class/password payloads
        assert "teacher" not in set_cookie.split("session_id=")[1].split(";")[0]
        assert _session_count(test_db) == 1

    def test_login_reissues_new_session_id(self, flask_app, test_db):
        """Login with an existing session: old id invalidated, new id issued."""
        client = flask_app.test_client()
        r1 = client.post(
            "/auth/login",
            json={"username": "teacher_a", "password": "teacher_a_pass"},
        )
        old_cookie = r1.headers.get("Set-Cookie", "").split(";")[0]

        r2 = client.post(
            "/auth/login",
            json={"username": "teacher_a", "password": "teacher_a_pass"},
        )
        new_cookie = r2.headers.get("Set-Cookie", "").split(";")[0]
        assert old_cookie != new_cookie
        # Only one session row remains (old one deleted)
        assert _session_count(test_db) == 1

        # Old session id is dead: use a fresh client with the old cookie
        stale = flask_app.test_client()
        stale.set_cookie("session_id", old_cookie.split("=", 1)[1], domain="localhost")
        resp = stale.get("/auth/me")
        assert resp.status_code == 401

    def test_login_wrong_password(self, app_client):
        """Wrong password → 401 with same error as non-existent user."""
        resp = app_client.post(
            "/auth/login",
            json={"username": "teacher_a", "password": "wrong_password"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid credentials"

    def test_login_nonexistent_user(self, app_client):
        """Non-existent user → same 401 as wrong password (no user existence leak)."""
        resp = app_client.post(
            "/auth/login",
            json={"username": "ghost_user", "password": "anything"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid credentials"


class TestAuthRequired:
    def test_unauth_api_returns_401_json(self, app_client):
        """API request without session cookie → 401 JSON."""
        resp = app_client.get("/auth/me", headers={"Accept": "application/json"})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "unauthorized"

    def test_unauth_html_redirects_to_login(self, app_client):
        """Browser request (Accept: text/html) without session → 302 to /login."""
        resp = app_client.get("/me", headers={"Accept": "text/html"})
        assert resp.status_code == 302
        assert "/login?next=/me" in resp.headers["Location"]

    def test_identity_read_from_db_per_request(self, flask_app, test_db):
        """Role/class come from the users table per request, not a login snapshot."""
        client = flask_app.test_client()
        client.post(
            "/auth/login",
            json={"username": "student_a", "password": "student_a_pass"},
        )
        # Promote student_a to teacher directly in DB
        execute(test_db, "UPDATE users SET role = 'teacher' WHERE username = 'student_a'")
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.get_json()["user"]["role"] == "teacher"


class TestLogout:
    def test_logout_invalidates_session_immediately(self, flask_app, test_db):
        """Logout deletes the session row; the old cookie is dead right away."""
        client = flask_app.test_client()
        client.post(
            "/auth/login",
            json={"username": "student_a", "password": "student_a_pass"},
        )
        assert _session_count(test_db) == 1

        resp = client.post("/auth/logout")
        assert resp.status_code == 204
        assert _session_count(test_db) == 0

        resp = client.get("/auth/me")
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
