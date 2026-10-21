"""Campus MCP tool server (lesson 6).

A minimal MCP server over Streamable HTTP: one JSON-RPC 2.0 endpoint
(`POST /mcp`) implementing `initialize`, `tools/list` and `tools/call`,
plus a tokenless `GET /health` liveness check. Every /mcp request must carry
`Authorization: Bearer <MCP_AUTH_TOKEN>`; the token comes ONLY from the
environment (never committed, never baked into the image, never shown to the
frontend). Malformed requests return readable JSON-RPC errors.

Only the "tools" capability is exposed (lesson-6 scope).
"""
import os

from flask import Flask, jsonify, request

from tools import TOOLS, call_tool

app = Flask(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "campus-tools", "version": "1.0.0"}

JSON_PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601


def _authorized() -> bool:
    expected = (os.environ.get("MCP_AUTH_TOKEN") or "").strip()
    if not expected:
        return False  # no token configured -> reject everything
    header = request.headers.get("Authorization", "")
    return header == f"Bearer {expected}"


def _rpc_result(req_id, result):
    return jsonify({"jsonrpc": "2.0", "id": req_id, "result": result})


def _rpc_error(req_id, code, message):
    return jsonify({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/mcp")
def mcp():
    if not _authorized():
        return jsonify({"error": "unauthorized: valid Bearer token required"}), 401

    body = request.get_json(silent=True)
    if body is None:
        return _rpc_error(None, JSON_PARSE_ERROR, "请求体不是合法的 JSON")
    if not isinstance(body, dict) or not isinstance(body.get("method"), str):
        return _rpc_error(body.get("id") if isinstance(body, dict) else None,
                          INVALID_REQUEST, "缺少 method 字段或报文不是有效的 JSON-RPC 请求")

    req_id = body.get("id")
    method = body["method"]
    params = body.get("params") or {}
    if not isinstance(params, dict):
        return _rpc_error(req_id, INVALID_REQUEST, "params 必须是对象")

    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method == "tools/list":
        return _rpc_result(req_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _rpc_error(req_id, INVALID_REQUEST, "tools/call 缺少工具名 name")
        text, is_error = call_tool(name, params.get("arguments"))
        return _rpc_result(req_id, {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        })

    return _rpc_error(req_id, METHOD_NOT_FOUND, f"未知方法：{method}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
