"""GET /api/mcp/servers/{id}/tools — the cached discovery result.

Must be preceded by the connect case so the cache is populated.
"""


def path(ctx):
    return f"/api/mcp/servers/{ctx['mcp_server_id']}/tools"


def skip_if(ctx):
    return None if ctx.get("mcp_server_id") else "no seed server listed by the GET case"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    tools = {t["name"]: t for t in resp.json()["tools"]}
    assert set(tools) == {"formula_hint", "unit_convert"}, f"tools {list(tools)}"
    for name, tool in tools.items():
        assert tool["description"], f"{name} description empty"
        schema = tool["inputSchema"]
        assert schema.get("type") == "object", f"{name} schema not an object"
        assert schema.get("properties"), f"{name} schema has no properties"
    assert tools["formula_hint"]["inputSchema"]["required"] == ["query"]
    assert tools["unit_convert"]["inputSchema"]["required"] == [
        "value", "from_unit", "to_unit",
    ]


CASE = {
    "name": "教师查看服务器最近一次发现的工具清单（含 inputSchema）",
    "method": "GET",
    "path": path,
    "role": "teacher",
    "skip_if": skip_if,
    "check": check,
}
