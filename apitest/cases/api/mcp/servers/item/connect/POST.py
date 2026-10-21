"""POST /api/mcp/servers/{id}/connect — handshake + discovery against the demo server.

Asserts the connection succeeds, the status flips to connected, and the
discovered tool list (formula_hint + unit_convert) is cached.
"""


def path(ctx):
    return f"/api/mcp/servers/{ctx['mcp_server_id']}/connect"


def skip_if(ctx):
    return None if ctx.get("mcp_server_id") else "no seed server listed by the GET case"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:300]}"
    data = resp.json()
    server = data["server"]
    assert server["status"] == "connected"
    assert server["toolsCount"] == 2, f"expected 2 tools, got {server['toolsCount']}"
    assert '"token"' not in resp.text, "raw token must not appear in the response"

    tools = {t["name"]: t for t in data["tools"]}
    assert set(tools) == {"formula_hint", "unit_convert"}
    assert tools["unit_convert"]["inputSchema"]["required"] == [
        "value", "from_unit", "to_unit",
    ]

    # DB consistency: status + wholesale-replaced cache.
    from helpers import db_query_one

    row = db_query_one(
        "SELECT status FROM mcp_servers WHERE id = %s", (ctx["mcp_server_id"],)
    )
    assert row and row["status"] == "connected"
    cached = db_query_one(
        "SELECT COUNT(*) AS n FROM mcp_tools_cache WHERE server_id = %s",
        (ctx["mcp_server_id"],),
    )["n"]
    assert cached == 2, f"cache should hold 2 tools, got {cached}"


CASE = {
    "name": "教师连接 MCP 服务器（握手+发现，缓存整体替换为 2 个工具）",
    "method": "POST",
    "path": path,
    "role": "teacher",
    "skip_if": skip_if,
    "check": check,
}
