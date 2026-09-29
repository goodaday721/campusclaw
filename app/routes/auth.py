"""Auth routes: POST /auth/login, POST /auth/logout, GET /auth/me.

Server-side session scheme: the browser cookie holds only a random session id;
role and class are always read from the sessions+users tables per request.
"""
import bcrypt
from flask import Blueprint, current_app, g, jsonify, make_response, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.repositories import sessions as sessions_repo
from app.repositories.users import UserRepository

auth_bp = Blueprint("auth", __name__)

# Pre-computed dummy hash for constant-time user-not-found response
_DUMMY_HASH = bcrypt.hashpw(b"__nonexistent__", bcrypt.gensalt(rounds=12))


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """Authenticate with username+password and issue a NEW session (fixation defense)."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "invalid credentials"}), 401

    conn = get_connection(current_app.config["DB"])
    try:
        user_repo = UserRepository(conn)
        user = user_repo.find_by_username(username)
        # Use same timing path whether user exists or not
        stored_hash = user["password_hash"].encode("utf-8") if user else _DUMMY_HASH
        password_ok = bcrypt.checkpw(password.encode("utf-8"), stored_hash)

        if not user or not password_ok:
            return jsonify({"error": "invalid credentials"}), 401

        # Session fixation defense: discard the old session id, issue a new one
        old_token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
        sessions_repo.delete(conn, old_token)
        token = sessions_repo.create(conn, user["id"], current_app.config["SESSION_TTL_HOURS"])
    finally:
        conn.close()

    resp = make_response(
        jsonify({"user": {"id": user["id"], "role": user["role"], "classId": user["class_id"]}}),
        200,
    )
    resp.set_cookie(
        current_app.config["SESSION_COOKIE_NAME"],
        token,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return resp


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """Delete the server-side session row; the session is invalid immediately."""
    conn = get_connection(current_app.config["DB"])
    try:
        token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
        sessions_repo.delete(conn, token)
    finally:
        conn.close()

    resp = make_response("", 204)
    resp.delete_cookie(current_app.config["SESSION_COOKIE_NAME"], path="/")
    return resp


@auth_bp.route("/auth/me", methods=["GET"])
@auth_required
def me():
    """Return the current authenticated user's info."""
    return jsonify({"user": g.current_user}), 200
