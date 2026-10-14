"""GET/PUT /api/prompt — the class-level system prompt (lesson 5).

Every logged-in member can read their own class's prompt; only teachers may
update it (students get 403). Answers read the prompt from the database on
every generation, so a saved prompt takes effect from the next turn.
"""
from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import prompts as prompts_repo

prompt_bp = Blueprint("api_prompt", __name__)


@prompt_bp.route("/api/prompt", methods=["GET"])
@auth_required
def get_prompt():
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        body = prompts_repo.get(conn, class_id)
    finally:
        conn.close()
    return jsonify({"classId": class_id, "body": body or ""}), 200


@prompt_bp.route("/api/prompt", methods=["PUT"])
@auth_required
@role_required("teacher")
def put_prompt():
    body = request.get_json(silent=True) or {}
    text = body.get("body")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "body must not be empty"}), 400

    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        prompts_repo.upsert(conn, class_id, text.strip())
        conn.commit()
    finally:
        conn.close()
    return jsonify({"classId": class_id, "body": text.strip()}), 200
