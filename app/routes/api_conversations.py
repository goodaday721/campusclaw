"""GET/POST /api/conversations, GET .../<id>, POST .../<id>/messages (lesson 5).

Conversations belong to their creator within their class; anything else reads
as 404 (other users' AND cross-class). The messages endpoint answers with an
SSE stream (meta -> delta* -> done); every pre-stream failure stays plain
JSON so the frontend can handle it like any other API error.
"""
from flask import Blueprint, Response, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.repositories import agents as agents_repo
from app.repositories import conversations as conversations_repo
from app.services import chat
from app.services import retrieval

conversations_bp = Blueprint("api_conversations", __name__)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds") + "Z"


def _conversation_dict(row: dict, agent_name: str | None = None) -> dict:
    return {
        "id": row["id"],
        "agentId": row["agent_id"],
        "agentName": agent_name if agent_name is not None else row.get("agent_name"),
        "title": row["title"],
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("updated_at")),
    }


def _message_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "citations": row["citations"],
        "skillName": row.get("skill_name"),
        "createdAt": _iso(row.get("created_at")),
    }


@conversations_bp.route("/api/conversations", methods=["GET"])
@auth_required
def list_conversations():
    conn = get_connection(current_app.config["DB"])
    try:
        rows = conversations_repo.list_by_user(
            conn, g.current_user["userId"], g.current_user["classId"]
        )
    finally:
        conn.close()
    return jsonify({"conversations": [_conversation_dict(r) for r in rows]}), 200


@conversations_bp.route("/api/conversations", methods=["POST"])
@auth_required
def create_conversation():
    body = request.get_json(silent=True) or {}
    agent_id = body.get("agent_id")
    if not isinstance(agent_id, int) or isinstance(agent_id, bool):
        return jsonify({"error": "agent_id must be an integer"}), 400

    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        agent = agents_repo.find(conn, agent_id, class_id)
        if agent is None or (
            g.current_user["role"] == "student" and not agent["enabled"]
        ):
            return jsonify({"error": "not found"}), 404
        conversation_id = conversations_repo.create(
            conn, g.current_user["userId"], class_id, agent_id
        )
        conn.commit()
        row = conversations_repo.find_owned(
            conn, conversation_id, g.current_user["userId"], class_id
        )
    finally:
        conn.close()
    return jsonify({"conversation": _conversation_dict(row, agent["name"])}), 201


def _get_owned_or_404(conn, conversation_id: int):
    """Shared lookup: None unless the conversation belongs to this user+class."""
    return conversations_repo.find_owned(
        conn, conversation_id, g.current_user["userId"], g.current_user["classId"]
    )


@conversations_bp.route("/api/conversations/<int:conversation_id>", methods=["GET"])
@auth_required
def get_conversation(conversation_id: int):
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        row = _get_owned_or_404(conn, conversation_id)
        if row is None:
            return jsonify({"error": "not found"}), 404
        agent = agents_repo.find(conn, row["agent_id"], class_id)
        messages = conversations_repo.messages_for(conn, conversation_id)
    finally:
        conn.close()
    return jsonify(
        {
            "conversation": _conversation_dict(
                row, agent["name"] if agent else None
            ),
            "messages": [_message_dict(m) for m in messages],
        }
    ), 200


@conversations_bp.route(
    "/api/conversations/<int:conversation_id>/messages", methods=["POST"]
)
@auth_required
def post_message(conversation_id: int):
    body = request.get_json(silent=True) or {}
    content = body.get("content")
    if not isinstance(content, str) or not content.strip():
        return jsonify({"error": "content must not be empty"}), 400
    content = content.strip()

    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        row = _get_owned_or_404(conn, conversation_id)
        if row is None:
            return jsonify({"error": "not found"}), 404
        agent = agents_repo.find(conn, row["agent_id"], class_id)
        if agent is None or (
            g.current_user["role"] == "student" and not agent["enabled"]
        ):
            return jsonify({"error": "not found"}), 404
    finally:
        conn.close()

    # All pre-stream failures stay plain JSON (503/400); only after the
    # gateway stream is successfully primed do we switch to SSE.
    try:
        result = chat.start(
            current_app.config["DB"],
            current_app.config["QDRANT"],
            current_app.config["APP_CONFIG"],
            class_id,
            agent,
            conversation_id,
            content,
        )
    except chat.AnswerUnavailable as exc:
        return jsonify({"error": "answer service unavailable", "detail": str(exc)}), 503
    except retrieval.EmptyQuery as exc:
        return jsonify({"error": str(exc)}), 400

    response = Response(
        chat.sse_stream(result, current_app.config["DB"], conversation_id, content),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    # Disable proxy buffering (Nginx) so deltas reach the browser as they go.
    response.headers["X-Accel-Buffering"] = "no"
    return response
