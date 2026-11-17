"""GET/POST /api/skills, PUT/DELETE /api/skills/<id> — guided skills (lesson 5).

Skills are authored as a single source text block and parsed server-side
(see app.services.skill_source). Everything is class-scoped: cross-class
skills read as 404. Students may read enabled skills only; all writes are
teacher-only (403 for students).

Lesson 11 拓展 adds POST /api/skills/import: a teacher uploads a .md (source
text) or .json skill package. The file is parsed, tool references are checked
exactly like a manual create, and the skill is stored **disabled** so it can be
reviewed in the list before being enabled.
"""
import json
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import skills as skills_repo
from app.services import audit, skill_source
from app.services.mcp_service import ReferenceError_, validate_reference
from app.services.skill_source import SkillSourceError

skills_bp = Blueprint("api_skills", __name__)

IMPORT_MAX_BYTES = 64 * 1024
IMPORT_EXTENSIONS = {".md", ".json"}


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
    audit.record(
        current_app.config["DB"],
        class_id=g.current_user["classId"],
        actor_id=g.current_user["userId"],
        action="create",
        target_type="skill",
        target_id=skill_id,
        skill_name=created["name"],
        detail={"enabled": bool(created["enabled"])},
    )
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
    audit.record(
        current_app.config["DB"],
        class_id=class_id,
        actor_id=g.current_user["userId"],
        action="update",
        target_type="skill",
        target_id=skill_id,
        skill_name=updated["name"],
        detail={"enabled": bool(updated["enabled"])},
    )
    return jsonify({"skill": _serialize(updated)}), 200


@skills_bp.route("/api/skills/<int:skill_id>", methods=["DELETE"])
@auth_required
@role_required("teacher")
def delete_skill(skill_id: int):
    conn = get_connection(current_app.config["DB"])
    try:
        existing = skills_repo.find(conn, skill_id, g.current_user["classId"])
        if existing is None:
            return jsonify({"error": "not found"}), 404
        skills_repo.delete(conn, skill_id)
        conn.commit()
    finally:
        conn.close()
    audit.record(
        current_app.config["DB"],
        class_id=g.current_user["classId"],
        actor_id=g.current_user["userId"],
        action="delete",
        target_type="skill",
        target_id=skill_id,
        skill_name=existing["name"],
    )
    return "", 204


def _fields_from_json(text: str) -> dict:
    """Accept either {"source": "..."} or flat {name, description, trigger, tools}."""
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise SkillSourceError("file must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise SkillSourceError("JSON body must be an object")
    if isinstance(payload.get("source"), str) and payload["source"].strip():
        return skill_source.parse(payload["source"])
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not name:
        raise SkillSourceError("JSON must contain name (or source)")
    if not description:
        raise SkillSourceError("JSON must contain description (or source)")
    tools = payload.get("tools") or []
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise SkillSourceError("tools must be an array of strings")
    return {
        "name": name,
        "trigger": str(payload.get("trigger") or "").strip(),
        "tools": [t.strip() for t in tools if t.strip()],
        "subject": str(payload.get("subject") or "").strip(),
        "description": description,
        "enabled": False,
    }


def _canonical_source(fields: dict) -> str:
    """Render parsed fields back to the single-source text so the editor works."""
    lines = [f"名称：{fields['name']}"]
    if fields.get("trigger"):
        lines.append(f"适用条件：{fields['trigger']}")
    if fields.get("tools"):
        lines.append("工具：" + ", ".join(fields["tools"]))
    if fields.get("subject"):
        lines.append(f"资料：{fields['subject']}")
    lines.append("启用：否")  # imports always land disabled
    return "\n".join(lines) + "\n\n" + fields["description"]


@skills_bp.route("/api/skills/import", methods=["POST"])
@auth_required
@role_required("teacher")
def import_skill():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "file is required"}), 400
    filename = Path(upload.filename).name
    ext = Path(filename).suffix.lower()
    if ext not in IMPORT_EXTENSIONS:
        return jsonify({"error": f"file type not allowed: {ext}"}), 415
    raw = upload.read(IMPORT_MAX_BYTES + 1)
    if len(raw) > IMPORT_MAX_BYTES:
        return jsonify({"error": "file too large"}), 413
    try:
        # utf-8-sig also strips a Windows/Notepad BOM, which would otherwise
        # break the first `名称：` line match.
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "file must be UTF-8 text"}), 400

    try:
        fields = _fields_from_json(text) if ext == ".json" else skill_source.parse(text)
    except SkillSourceError as exc:
        return jsonify({"error": str(exc)}), 400

    fields["enabled"] = False
    fields["source"] = _canonical_source(fields)
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        for existing in skills_repo.list_by_class(conn, class_id):
            if existing["name"] == fields["name"]:
                return jsonify({"error": f"skill already exists: {fields['name']}"}), 409
        error = _validate_tools(conn, class_id, fields)
        if error:
            return error
        skill_id = skills_repo.create(conn, class_id, fields)
        conn.commit()
        created = skills_repo.find(conn, skill_id, class_id)
    finally:
        conn.close()

    audit.record(
        current_app.config["DB"],
        class_id=class_id,
        actor_id=g.current_user["userId"],
        action="create",
        target_type="skill",
        target_id=skill_id,
        skill_name=created["name"],
        detail={"import": True, "filename": filename, "enabled": False},
    )
    return jsonify({"skill": _serialize(created)}), 201
