"""GET /api/audit-logs — teacher-only, class-scoped audit records (SEC-07).

Returns the newest `limit` rows for the caller's class, optionally filtered by
`action` (create/update/delete/download/submit/grade/explain/login/logout/
connect/disconnect) or `target_type` (material/skill/agent/prompt/
mcp_server/assignment/submission/wrong_question/session).

Each row carries the seven SEC-07 columns: action, target_type, target_id,
actor_id, class_id, skill_name and detail (usage/duration JSON).
"""
import json

from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import audit as audit_repo

audit_bp = Blueprint("api_audit", __name__)

_ACTIONS = {
    "login", "logout", "create", "update", "delete", "download",
    "submit", "grade", "explain", "connect", "disconnect", "reindex",
}
_TARGETS = {
    "session", "material", "skill", "agent", "prompt", "mcp_server",
    "assignment", "submission", "wrong_question", "conversation",
}


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds") + "Z"


def _row_dict(row: dict) -> dict:
    detail = row.get("detail")
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            pass
    return {
        "id": row["id"],
        "classId": row["class_id"],
        "actorId": row["actor_id"],
        "action": row["action"],
        "targetType": row["target_type"],
        "targetId": row["target_id"],
        "skillName": row["skill_name"],
        "detail": detail,
        "createdAt": _iso(row.get("created_at")),
    }


@audit_bp.route("/api/audit-logs", methods=["GET"])
@auth_required
@role_required("teacher")
def list_audit_logs():
    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit or 50, 200))
    action = request.args.get("action")
    target_type = request.args.get("target_type")
    if action and action not in _ACTIONS:
        return jsonify({"error": f"unknown action: {action}"}), 400
    if target_type and target_type not in _TARGETS:
        return jsonify({"error": f"unknown target_type: {target_type}"}), 400

    conn = get_connection(current_app.config["DB"])
    try:
        rows = audit_repo.list_by_class(
            conn,
            g.current_user["classId"],
            limit=limit,
            action=action,
            target_type=target_type,
        )
    finally:
        conn.close()
    return jsonify({"audit_logs": [_row_dict(r) for r in rows]}), 200
