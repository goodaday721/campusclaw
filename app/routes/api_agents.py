"""GET/POST /api/agents, GET/PUT /api/agents/<id> — assistant agents (lesson 5).

An agent = {name, prompt, skill_ids[], material_ids[], enabled}. Prompt empty
falls back to the class prompt at answer time. Bound skills/materials must
belong to the agent's class (404 otherwise). Students see enabled agents only
and may never modify them (403) — permissions live server-side.
"""
from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import agents as agents_repo
from app.repositories import skills as skills_repo
from app.repositories.materials import MaterialsRepository

agents_bp = Blueprint("api_agents", __name__)


def _serialize(agent: dict) -> dict:
    return {
        "id": agent["id"],
        "classId": agent["class_id"],
        "name": agent["name"],
        "prompt": agent["prompt"],
        "skillIds": agent["skillIds"],
        "materialIds": agent["materialIds"],
        "enabled": agent["enabled"],
    }


def _parse_body():
    """Parse and structurally validate the agent payload → (dict, error)."""
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, (jsonify({"error": "name must not be empty"}), 400)

    prompt = body.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        return None, (jsonify({"error": "prompt must be a string"}), 400)

    def _id_list(key):
        value = body.get(key)
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            return None
        return list(dict.fromkeys(value))  # de-duplicate, keep order

    skill_ids = _id_list("skill_ids")
    if skill_ids is None:
        return None, (jsonify({"error": "skill_ids must be a list of ids"}), 400)
    material_ids = _id_list("material_ids")
    if material_ids is None:
        return None, (jsonify({"error": "material_ids must be a list of ids"}), 400)

    return (
        {
            "name": name.strip(),
            "prompt": prompt,
            "skill_ids": skill_ids,
            "material_ids": material_ids,
            "enabled": bool(body.get("enabled", True)),
        },
        None,
    )


def _validate_bindings(conn, class_id: int, parsed: dict) -> str | None:
    """Ensure every bound skill/material belongs to the class; error or None."""
    for sid in parsed["skill_ids"]:
        if skills_repo.find(conn, sid, class_id) is None:
            return f"skill {sid} not found in this class"
    repo = MaterialsRepository(conn)
    for mid in parsed["material_ids"]:
        if repo.find_by_id_scoped_to_class(mid, class_id) is None:
            return f"material {mid} not found in this class"
    return None


@agents_bp.route("/api/agents", methods=["GET"])
@auth_required
def list_agents():
    enabled_only = g.current_user["role"] == "student"
    conn = get_connection(current_app.config["DB"])
    try:
        rows = agents_repo.list_by_class(
            conn, g.current_user["classId"], enabled_only=enabled_only
        )
    finally:
        conn.close()
    return jsonify({"agents": [_serialize(r) for r in rows]}), 200


@agents_bp.route("/api/agents", methods=["POST"])
@auth_required
@role_required("teacher")
def create_agent():
    parsed, error = _parse_body()
    if error:
        return error
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        conflict = _validate_bindings(conn, class_id, parsed)
        if conflict:
            return jsonify({"error": conflict}), 404
        agent_id = agents_repo.create(conn, class_id, **parsed)
        conn.commit()
        created = agents_repo.find(conn, agent_id, class_id)
    finally:
        conn.close()
    return jsonify({"agent": _serialize(created)}), 201


@agents_bp.route("/api/agents/<int:agent_id>", methods=["GET"])
@auth_required
def get_agent(agent_id: int):
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        agent = agents_repo.find(conn, agent_id, class_id)
        if agent is None or (
            g.current_user["role"] == "student" and not agent["enabled"]
        ):
            return jsonify({"error": "not found"}), 404
    finally:
        conn.close()
    return jsonify({"agent": _serialize(agent)}), 200


@agents_bp.route("/api/agents/<int:agent_id>", methods=["PUT"])
@auth_required
@role_required("teacher")
def update_agent(agent_id: int):
    parsed, error = _parse_body()
    if error:
        return error
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        if agents_repo.find(conn, agent_id, class_id) is None:
            return jsonify({"error": "not found"}), 404
        conflict = _validate_bindings(conn, class_id, parsed)
        if conflict:
            return jsonify({"error": conflict}), 404
        agents_repo.update(conn, agent_id, **parsed)
        conn.commit()
        updated = agents_repo.find(conn, agent_id, class_id)
    finally:
        conn.close()
    return jsonify({"agent": _serialize(updated)}), 200
