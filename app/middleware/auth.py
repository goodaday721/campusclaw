"""Authentication middleware: session-cookie parsing and auth_required decorator."""
from functools import wraps

from flask import current_app, g, jsonify, redirect, request

from app.db.connection import get_connection
from app.repositories import sessions as sessions_repo


def auth_required(f):
    """Decorator that requires a valid server-side session cookie.

    Resolves identity from the sessions+users tables on EVERY request, so
    role/class changes in the database take effect immediately.
    - API requests (Accept: application/json or no text/html) → 401 JSON
    - Browser page requests (Accept: text/html) → 302 redirect to /login?next=<path>
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
        conn = get_connection(current_app.config["DB"])
        try:
            row = sessions_repo.find_valid(conn, token)
        finally:
            conn.close()
        if row is None:
            return _reject()

        g.current_user = {
            "userId": row["user_id"],
            "role": row["role"],
            "classId": row["class_id"],
        }
        return f(*args, **kwargs)

    return decorated


def _reject():
    """Return 401 JSON for API requests, 302 redirect for page requests."""
    accept = request.headers.get("Accept", "")
    if "text/html" in accept and "application/json" not in accept:
        next_path = request.path
        return redirect(f"/login?next={next_path}", code=302)
    return jsonify({"error": "unauthorized"}), 401
