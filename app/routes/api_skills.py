"""GET/POST /api/skills, PUT/DELETE /api/skills/<id> — guided skills (lesson 5).

Skills are authored as a single source text block and parsed server-side
(see app.services.skill_source). Everything is class-scoped: cross-class
skills read as 404. Students may read enabled skills only; all writes are
teacher-only (403 for students).
"""
from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import skills as skills_repo
from app.services import skill_source
from app.services.mcp_service import ReferenceError_, validate_reference
from app.services.skill_source import SkillSourceError

skills_bp = Blueprint("api_skills", __name__)


def _serialize(skill: dict) -> dict:
    return {
        "id": skill["id"],
        "classId": skill["class_id"],
        "name": skill["name"],
        "trigger": skill["trigger"],
        "tools": skill["tools"],
        "subject": skill["subject"],
        "description": skill["description"],
        "source": skill["source"],
        "enabled": skill["enabled"],
    }


def _parse_body():
    """Parse {source} from the request; returns (fields, error_response)."""
    body = request.get_json(silent=True) or {}
    source = body.get("source")
    if not isinstance(source, str) or not source.strip():
        return None, (jsonify({"error": "source must not be empty"}), 400)
    try:
        return skill_source.parse(source), None
    except SkillSourceError as exc:
        return None, (jsonify({"error": str(exc)}), 400)


def _validate_tools(conn, class_id: int, fields: dict):
    """Config-time MCP reference checks; returns an error response or None."""
    for tool in fields.get("tools") or []:
        try:
            validate_reference(conn, class_id, tool)
        except ReferenceError_ as exc:
            return jsonify({"error": str(exc)}), 400
    return None


@skills_bp.route("/api/skills", methods=["GET"])
@auth_required
def list_skills():
    enabled_only = g.current_user["role"] == "student"
    conn = get_connection(current_app.config["DB"])
    try:
        rows = skills_repo.list_by_class(
            conn, g.current_user["classId"], enabled_only=enabled_only
        )
    finally:
        conn.close()
    return jsonify({"skills": [_serialize(r) for r in rows]}), 200


@skills_bp.route("/api/skills", methods=["POST"])
@auth_required
@role_required("teacher")
def create_skill():
    fields, error = _parse_body()
    if error:
        return error
    conn = get_connection(current_app.config["DB"])
    try:
        error = _validate_tools(conn, g.current_user["classId"], fields)
        if error:
            return error
        skill_id = skills_repo.create(conn, g.current_user["classId"], fields)
        conn.commit()
        created = skills_repo.find(conn, skill_id, g.current_user["classId"])
    finally:
        conn.close()
    return jsonify({"skill": _serialize(created)}), 201


@skills_bp.route("/api/skills/<int:skill_id>", methods=["PUT"])
@auth_required
@role_required("teacher")
def update_skill(skill_id: int):
    fields, error = _parse_body()
    if error:
        return error
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        if skills_repo.find(conn, skill_id, class_id) is None:
            return jsonify({"error": "not found"}), 404
        error = _validate_tools(conn, class_id, fields)
        if error:
            return error
        skills_repo.update(conn, skill_id, fields)
        conn.commit()
        updated = skills_repo.find(conn, skill_id, class_id)
    finally:
        conn.close()
    return jsonify({"skill": _serialize(updated)}), 200


@skills_bp.route("/api/skills/<int:skill_id>", methods=["DELETE"])
@auth_required
@role_required("teacher")
def delete_skill(skill_id: int):
    conn = get_connection(current_app.config["DB"])
    try:
        if skills_repo.find(conn, skill_id, g.current_user["classId"]) is None:
            return jsonify({"error": "not found"}), 404
        skills_repo.delete(conn, skill_id)
        conn.commit()
    finally:
        conn.close()
    return "", 204
