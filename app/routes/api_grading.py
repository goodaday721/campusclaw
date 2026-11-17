"""Lesson-8 grading routes: assignments + submissions + async task polling.

POST/GET /api/assignments                        (teacher creates / class lists)
POST     /api/assignments/<id>/submissions       (student submits → 202 + taskId)
GET      /api/submissions/<id>                   (owner student or class teacher)

Cross-class ids and "not mine" submissions both read as 404. Repeated submits
reuse the same submission and task (idempotency anchor: one row per
assignment+student, one job per submission).
"""
from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import grading as grading_repo
from app.services import audit

grading_bp = Blueprint("api_grading", __name__)

_MAX_ATTEMPTS = 3


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds") + "Z"


def _assignment_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "classId": row["class_id"],
        "title": row["title"],
        "question": row["question"],
        "referenceAnswer": row["reference_answer"],
        "createdBy": row["created_by"],
        "createdAt": _iso(row.get("created_at")),
    }


def _submission_dict(row: dict, task_id: int | None = None) -> dict:
    data = {
        "id": row["id"],
        "assignmentId": row["assignment_id"],
        "classId": row["class_id"],
        "studentId": row["student_id"],
        "answer": row["answer"],
        "status": row["status"],
        "score": row["score"],
        "feedback": row["feedback"],
        "gradedAt": _iso(row.get("graded_at")),
        "createdAt": _iso(row.get("created_at")),
    }
    if task_id is not None:
        data["taskId"] = task_id
    return data


@grading_bp.route("/api/assignments", methods=["GET"])
@auth_required
def list_assignments():
    conn = get_connection(current_app.config["DB"])
    try:
        rows = grading_repo.list_assignments(conn, g.current_user["classId"])
    finally:
        conn.close()
    return jsonify({"assignments": [_assignment_dict(r) for r in rows]}), 200


@grading_bp.route("/api/assignments", methods=["POST"])
@auth_required
@role_required("teacher")
def create_assignment():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    question = (body.get("question") or "").strip()
    reference = (body.get("reference_answer") or "").strip()
    if not title or not question or not reference:
        return jsonify({"error": "title、question、reference_answer 必填"}), 400

    conn = get_connection(current_app.config["DB"])
    try:
        assignment_id = grading_repo.create_assignment(
            conn, g.current_user["classId"], title, question, reference,
            g.current_user["userId"],
        )
        conn.commit()
        row = grading_repo.find_assignment(
            conn, assignment_id, g.current_user["classId"]
        )
    finally:
        conn.close()
    audit.record(
        current_app.config["DB"],
        class_id=g.current_user["classId"],
        actor_id=g.current_user["userId"],
        action="create",
        target_type="assignment",
        target_id=assignment_id,
        detail={"title": title},
    )
    return jsonify({"assignment": _assignment_dict(row)}), 201


@grading_bp.route(
    "/api/assignments/<int:assignment_id>/submissions", methods=["POST"]
)
@auth_required
def submit_assignment(assignment_id: int):
    if g.current_user["role"] != "student":
        return jsonify({"error": "仅学生可提交作业"}), 403
    body = request.get_json(silent=True) or {}
    answer = (body.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "answer 必填"}), 400

    class_id = g.current_user["classId"]
    student_id = g.current_user["userId"]
    conn = get_connection(current_app.config["DB"])
    try:
        assignment = grading_repo.find_assignment(conn, assignment_id, class_id)
        if assignment is None:
            return jsonify({"error": "not found"}), 404

        # Submission + job are one transaction: no submission without a task.
        submission_id, _created = grading_repo.upsert_submission(
            conn, assignment_id, class_id, student_id, answer
        )
        dedupe_key = f"grade:{submission_id}"
        task_id = grading_repo.enqueue(
            conn, class_id, "grade", dedupe_key,
            {"submission_id": submission_id}, max_attempts=_MAX_ATTEMPTS,
        )
        conn.commit()
        job = grading_repo.find_job(conn, task_id)
    finally:
        conn.close()
    audit.record(
        current_app.config["DB"],
        class_id=class_id,
        actor_id=student_id,
        action="submit",
        target_type="submission",
        target_id=submission_id,
        detail={"assignmentId": assignment_id, "taskId": task_id},
    )
    return jsonify({
        "taskId": task_id,
        "submissionId": submission_id,
        "status": (job or {}).get("status", "pending"),
    }), 202


@grading_bp.route("/api/submissions/<int:submission_id>", methods=["GET"])
@auth_required
def get_submission(submission_id: int):
    user = g.current_user
    conn = get_connection(current_app.config["DB"])
    try:
        row = grading_repo.find_submission(conn, submission_id, user["classId"])
        if row is None:
            return jsonify({"error": "not found"}), 404
        if user["role"] == "student" and row["student_id"] != user["userId"]:
            return jsonify({"error": "not found"}), 404
        job = grading_repo.find_job_by_dedupe(conn, f"grade:{submission_id}")
    finally:
        conn.close()
    return jsonify(
        _submission_dict(row, task_id=(job or {}).get("id"))
    ), 200
