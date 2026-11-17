"""Wrong questions routes (lesson 11 必做: 错题本 + 错题讲解).

GET  /api/wrong-questions                    (student: own / teacher: whole class)
GET  /api/wrong-questions/<int:wq_id>        (owner student or class teacher)
POST /api/wrong-questions/<int:wq_id>/explain  (SSE stream, owner or class teacher)

Cross-class ids, cross-student ids and missing ids all read as the same 404.
The explain endpoint reuses the chat pipeline: it creates a fresh conversation
bound to the class's default enabled agent, seeds it with a synthetic user
message that carries the question/student answer/reference answer/reason, and
lets the seeded "错题讲解" skill drive the model.
"""
from flask import Blueprint, Response, current_app, g, jsonify

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.repositories import agents as agents_repo
from app.repositories import conversations as conversations_repo
from app.repositories import wrong_questions as wq_repo
from app.services import audit, chat
from app.services import retrieval

wrong_questions_bp = Blueprint("api_wrong_questions", __name__)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds") + "Z"


def _wq_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "classId": row["class_id"],
        "submissionId": row["submission_id"],
        "studentId": row["student_id"],
        "question": row["question"],
        "studentAnswer": row["student_answer"],
        "referenceAnswer": row["reference_answer"],
        "reason": row["reason"],
        "createdAt": _iso(row.get("created_at")),
    }


def _load_scoped(conn, wq_id: int, user: dict) -> dict | None:
    """Class-scoped read; students also locked to their own rows."""
    student_id = user["userId"] if user["role"] == "student" else None
    return wq_repo.find_by_id_scoped(conn, wq_id, user["classId"], student_id)


@wrong_questions_bp.route("/api/wrong-questions", methods=["GET"])
@auth_required
def list_wrong_questions():
    user = g.current_user
    conn = get_connection(current_app.config["DB"])
    try:
        if user["role"] == "student":
            rows = wq_repo.list_for_student(conn, user["userId"], user["classId"])
        else:
            rows = wq_repo.list_for_class(conn, user["classId"])
    finally:
        conn.close()
    return jsonify({"wrong_questions": [_wq_dict(r) for r in rows]}), 200


@wrong_questions_bp.route("/api/wrong-questions/<int:wq_id>", methods=["GET"])
@auth_required
def get_wrong_question(wq_id: int):
    conn = get_connection(current_app.config["DB"])
    try:
        row = _load_scoped(conn, wq_id, g.current_user)
    finally:
        conn.close()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(_wq_dict(row)), 200


@wrong_questions_bp.route(
    "/api/wrong-questions/<int:wq_id>/explain", methods=["POST"]
)
@auth_required
def explain_wrong_question(wq_id: int):
    user = g.current_user
    class_id = user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        wq = _load_scoped(conn, wq_id, user)
        if wq is None:
            return jsonify({"error": "not found"}), 404
        agents = agents_repo.list_by_class(conn, class_id, enabled_only=True)
        if not agents:
            return jsonify({"error": "no enabled agent for this class"}), 503
        agent = agents[0]
        conversation_id = conversations_repo.create(
            conn, user["userId"], class_id, agent["id"]
        )
        conn.commit()
    finally:
        conn.close()

    audit.record(
        current_app.config["DB"],
        class_id=class_id,
        actor_id=user["userId"],
        action="explain",
        target_type="wrong_question",
        target_id=wq_id,
        skill_name="错题讲解",
        detail={"conversationId": conversation_id, "agentId": agent["id"]},
    )

    content = (
        "请讲解这道我做错的题。\n\n"
        f"题目：\n{wq['question']}\n\n"
        f"我的答案：\n{wq['student_answer']}\n\n"
        f"参考答案：\n{wq['reference_answer']}\n\n"
        f"批改意见：{wq['reason']}"
    )

    try:
        result = chat.start(
            current_app.config["DB"],
            current_app.config["QDRANT"],
            current_app.config["APP_CONFIG"],
            class_id,
            agent,
            conversation_id,
            content,
            user_id=user["userId"],
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
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["X-Conversation-Id"] = str(conversation_id)
    return response
