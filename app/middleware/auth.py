"""Authentication middleware: Bearer JWT parsing and auth_required decorator."""
from functools import wraps

from flask import current_app, g, jsonify, redirect, request

from app.db.connection import get_connection
from app.repositories import sessions as sessions_repo
from app.services import token_auth


def auth_required(f):
    """Decorator that requires a valid Bearer JWT with a live server-side session.

    Validates the JWT signature/expiry, checks the jti against the sessions
    table (revocation), and resolves identity from the users table on EVERY
    request, so role/class changes in the database take effect immediately.
    - API requests (Accept: application/json or no text/html) → 401 JSON
    - Browser page requests (Accept: text/html) → 302 redirect to /login?next=<path>
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _bearer_token()
        jti = None
        if token:
            try:
                payload = token_auth.verify(current_app.config["APP_CONFIG"], token)
                jti = payload["jti"]
            except token_auth.TokenInvalid:
                jti = None

        conn = get_connection(current_app.config["DB"])
        try:
            row = sessions_repo.find_valid(conn, jti)
        finally:
            conn.close()
        if row is None:
            return _reject()

        g.current_user = {
            "userId": row["user_id"],
            "role": row["role"],
            "classId": row["class_id"],
        }
        g.token_jti = jti
        return f(*args, **kwargs)

    return decorated


def _bearer_token() -> str | None:
    """Extract the token from an ``Authorization: Bearer <jwt>`` header."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        value = header[7:].strip()
        return value or None
    return None


def _reject():
    """Return 401 JSON for API requests, 302 redirect for page requests."""
    accept = request.headers.get("Accept", "")
    if "text/html" in accept and "application/json" not in accept:
        next_path = request.path
        return redirect(f"/login?next={next_path}", code=302)
    return jsonify({"error": "unauthorized"}), 401
