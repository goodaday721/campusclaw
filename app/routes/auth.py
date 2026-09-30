"""Auth routes: POST /auth/login, POST /auth/logout, GET /auth/me.

Bearer-token scheme: login issues an HS256 JWT (payload: sub/jti/iat/exp)
and registers its jti in the server-side sessions table for revocation;
role and class are always read from the users table per request.
"""
import bcrypt
from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.repositories import sessions as sessions_repo
from app.repositories.users import UserRepository
from app.services import token_auth

auth_bp = Blueprint("auth", __name__)

# Pre-computed dummy hash for constant-time user-not-found response
_DUMMY_HASH = bcrypt.hashpw(b"__nonexistent__", bcrypt.gensalt(rounds=12))


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """Authenticate with username+password and issue a JWT bearer token."""
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

        config = current_app.config["APP_CONFIG"]
        token, jti, expires_at = token_auth.issue(config, user["id"])
        sessions_repo.create(conn, jti, user["id"], expires_at)
    finally:
        conn.close()

    return (
        jsonify(
            {
                "token": token,
                "user": {"id": user["id"], "role": user["role"], "classId": user["class_id"]},
            }
        ),
        200,
    )


@auth_bp.route("/auth/logout", methods=["POST"])
@auth_required
def logout():
    """Delete the server-side session row; the token is invalid immediately."""
    conn = get_connection(current_app.config["DB"])
    try:
        sessions_repo.delete(conn, g.token_jti)
    finally:
        conn.close()

    return jsonify({"ok": True}), 200


@auth_bp.route("/auth/me", methods=["GET"])
@auth_required
def me():
    """Return the current authenticated user's info."""
    return jsonify({"user": g.current_user}), 200
