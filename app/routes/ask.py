"""POST /ask — grounded QA with citations; no evidence, no generation."""
from flask import Blueprint, current_app, g, jsonify, request

from app.middleware.auth import auth_required
from app.services import answer as answer_service
from app.services import retrieval

ask_bp = Blueprint("ask", __name__)


@ask_bp.route("/ask", methods=["POST"])
@auth_required
def ask():
    body = request.get_json(silent=True) or {}
    # class_id from the body is deliberately ignored — session class only.
    question = body.get("question", "")
    history = body.get("history")

    if question is None or not str(question).strip():
        return jsonify({"error": "question must not be empty"}), 400

    try:
        result = answer_service.build_answer(
            current_app.config["DB"],
            current_app.config["QDRANT"],
            current_app.config["APP_CONFIG"],
            g.current_user["classId"],
            str(question),
            history=history,
        )
    except answer_service.AnswerUnavailable as exc:
        return jsonify({"error": "answer service unavailable", "detail": str(exc)}), 503
    except retrieval.EmptyQuery as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 200
