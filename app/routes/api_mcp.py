"""Teacher-side MCP registry routes (lesson 6).

GET/POST /api/mcp/servers, PUT/DELETE /api/mcp/servers/<id>,
POST .../connect (handshake + discovery, cache wholesale-replaced),
POST .../disconnect (cache emptied, unusable), GET .../tools (cached
discovery), GET /api/mcp/call-logs (class audit).

Everything is teacher-only (students 403). Cross-class ids read as 404 —
byte-identical to "does not exist". No response ever carries the raw token:
list/detail shapes expose only a hasToken boolean.
"""
from flask import Blueprint, current_app, g, jsonify, request

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories import mcp as mcp_repo
from app.services import mcp_client
from app.services.mcp_client import McpError

mcp_bp = Blueprint("api_mcp", __name__)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds") + "Z"


def _server_dict(row: dict, tools_count: int | None = None) -> dict:
    data = {
        "id": row["id"],
        "classId": row["class_id"],
        "name": row["name"],
        "baseUrl": row["base_url"],
        "hasToken": bool(row.get("has_token", row.get("token"))),
        "status": row["status"],
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("updated_at")),
    }
    if tools_count is not None:
        data["toolsCount"] = tools_count
    return data


def _tool_dict(row: dict) -> dict:
    return {
        "name": row["name"],
        "description": row.get("description") or "",
        "inputSchema": row.get("input_schema") or {},
    }


def _call_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "ref": f"{row['tool_name']}@{row['server_name']}",
        "serverName": row["server_name"],
        "toolName": row["tool_name"],
        "status": row["status"],
        "detail": row.get("detail"),
        "userId": row["user_id"],
        "conversationId": row["conversation_id"],
        "round": row["round_no"],
        "createdAt": _iso(row.get("created_at")),
    }


def _find_or_none(conn, server_id: int):
    return mcp_repo.find(conn, server_id, g.current_user["classId"])


@mcp_bp.route("/api/mcp/servers", methods=["GET"])
@auth_required
@role_required("teacher")
def list_servers():
    conn = get_connection(current_app.config["DB"])
    try:
        rows = mcp_repo.list_by_class(conn, g.current_user["classId"])
        out = []
        for row in rows:
            count = len(mcp_repo.tools_for_server(conn, row["id"]))
            out.append(_server_dict(row, tools_count=count))
    finally:
        conn.close()
    return jsonify({"servers": out}), 200


def _parse_server_body(require_all: bool):
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip() if body.get("name") is not None else None
    base_url = (body.get("base_url") or "").strip() if body.get("base_url") is not None else None
    token = body.get("token")
    token = token.strip() if isinstance(token, str) else token
    if require_all and (not name or not base_url):
        return None, (jsonify({"error": "name 与 base_url 必填"}), 400)
    if base_url is not None and not base_url.startswith(("http://", "https://")):
        return None, (jsonify({"error": "base_url 必须以 http:// 或 https:// 开头"}), 400)
    return {"name": name, "base_url": base_url, "token": token}, None


@mcp_bp.route("/api/mcp/servers", methods=["POST"])
@auth_required
@role_required("teacher")
def create_server():
    fields, error = _parse_server_body(require_all=True)
    if error:
        return error
    conn = get_connection(current_app.config["DB"])
    try:
        if mcp_repo.find_by_name(conn, fields["name"], g.current_user["classId"]) is not None:
            return jsonify({"error": "同名服务器已登记"}), 409
        server_id = mcp_repo.create(
            conn, g.current_user["classId"], fields["name"],
            fields["base_url"], fields["token"],
        )
        conn.commit()
        row = mcp_repo.find(conn, server_id, g.current_user["classId"])
    finally:
        conn.close()
    return jsonify({"server": _server_dict(row, tools_count=0)}), 201


@mcp_bp.route("/api/mcp/servers/<int:server_id>", methods=["PUT"])
@auth_required
@role_required("teacher")
def update_server(server_id: int):
    fields, error = _parse_server_body(require_all=False)
    if error:
        return error
    conn = get_connection(current_app.config["DB"])
    try:
        row = _find_or_none(conn, server_id)
        if row is None:
            return jsonify({"error": "not found"}), 404
        if fields["name"] and fields["name"] != row["name"]:
            dup = mcp_repo.find_by_name(conn, fields["name"], g.current_user["classId"])
            if dup is not None:
                return jsonify({"error": "同名服务器已登记"}), 409
        # Address/token changes invalidate the cached discovery + connection.
        mcp_repo.update(
            conn, server_id,
            name=fields["name"], base_url=fields["base_url"], token=fields["token"],
        )
        mcp_repo.clear_tools(conn, server_id)
        mcp_repo.set_status(conn, server_id, "disconnected")
        conn.commit()
        row = mcp_repo.find(conn, server_id, g.current_user["classId"])
    finally:
        conn.close()
    return jsonify({"server": _server_dict(row, tools_count=0)}), 200


@mcp_bp.route("/api/mcp/servers/<int:server_id>", methods=["DELETE"])
@auth_required
@role_required("teacher")
def delete_server(server_id: int):
    conn = get_connection(current_app.config["DB"])
    try:
        if _find_or_none(conn, server_id) is None:
            return jsonify({"error": "not found"}), 404
        mcp_repo.delete(conn, server_id)
        conn.commit()
    finally:
        conn.close()
    return "", 204


@mcp_bp.route("/api/mcp/servers/<int:server_id>/connect", methods=["POST"])
@auth_required
@role_required("teacher")
def connect_server(server_id: int):
    config = current_app.config["APP_CONFIG"]
    conn = get_connection(current_app.config["DB"])
    try:
        row = _find_or_none(conn, server_id)
        if row is None:
            return jsonify({"error": "not found"}), 404
        token = mcp_repo.raw_token(conn, server_id)

        # Connect = handshake + discovery, in order; any failure leaves the
        # server disconnected with an EMPTY cache (a failed discovery result
        # is never remembered) and a readable reason.
        try:
            mcp_client.initialize(row["base_url"], token, config)
            tools = mcp_client.list_tools(row["base_url"], token, config)
        except McpError as exc:
            mcp_repo.clear_tools(conn, server_id)
            mcp_repo.set_status(conn, server_id, "disconnected")
            conn.commit()
            return jsonify({
                "error": f"连接失败：{exc}",
                "status": "disconnected",
            }), 502

        mcp_repo.replace_tools(conn, server_id, tools)
        mcp_repo.set_status(conn, server_id, "connected")
        conn.commit()
        row = mcp_repo.find(conn, server_id, g.current_user["classId"])
        cached = mcp_repo.tools_for_server(conn, server_id)
    finally:
        conn.close()
    return jsonify({
        "server": _server_dict(row, tools_count=len(cached)),
        "tools": [_tool_dict(t) for t in cached],
    }), 200


@mcp_bp.route("/api/mcp/servers/<int:server_id>/disconnect", methods=["POST"])
@auth_required
@role_required("teacher")
def disconnect_server(server_id: int):
    conn = get_connection(current_app.config["DB"])
    try:
        if _find_or_none(conn, server_id) is None:
            return jsonify({"error": "not found"}), 404
        mcp_repo.clear_tools(conn, server_id)
        mcp_repo.set_status(conn, server_id, "disconnected")
        conn.commit()
        row = mcp_repo.find(conn, server_id, g.current_user["classId"])
    finally:
        conn.close()
    return jsonify({"server": _server_dict(row, tools_count=0)}), 200


@mcp_bp.route("/api/mcp/servers/<int:server_id>/tools", methods=["GET"])
@auth_required
@role_required("teacher")
def list_tools(server_id: int):
    conn = get_connection(current_app.config["DB"])
    try:
        row = _find_or_none(conn, server_id)
        if row is None:
            return jsonify({"error": "not found"}), 404
        cached = mcp_repo.tools_for_server(conn, server_id)
    finally:
        conn.close()
    return jsonify({"tools": [_tool_dict(t) for t in cached]}), 200


@mcp_bp.route("/api/mcp/call-logs", methods=["GET"])
@auth_required
@role_required("teacher")
def list_call_logs():
    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit or 50, 200))
    conn = get_connection(current_app.config["DB"])
    try:
        rows = mcp_repo.list_calls(conn, g.current_user["classId"], limit=limit)
    finally:
        conn.close()
    return jsonify({"calls": [_call_dict(r) for r in rows]}), 200
