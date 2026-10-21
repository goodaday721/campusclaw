"""POST /api/mcp/servers/{id}/disconnect — cache emptied, config-time rejects.

Runs last (z2 prefix) so the full chain above executes against a connected
server first. Also asserts that saving a skill referencing a tool on the now
disconnected server is rejected at save time.
"""
import time

import requests


def path(ctx):
    return f"/api/mcp/servers/{ctx['mcp_server_id']}/disconnect"


def skip_if(ctx):
    return None if ctx.get("mcp_server_id") else "no seed server listed by the GET case"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    server = resp.json()["server"]
    assert server["status"] == "disconnected", f"server status {server['status']}"
    assert server["toolsCount"] == 0, f"toolsCount {server['toolsCount']}"

    from helpers import db_query_one

    row = db_query_one(
        "SELECT status FROM mcp_servers WHERE id = %s", (ctx["mcp_server_id"],)
    )
    assert row and row["status"] == "disconnected", f"db row {row}"
    cached = db_query_one(
        "SELECT COUNT(*) AS n FROM mcp_tools_cache WHERE server_id = %s",
        (ctx["mcp_server_id"],),
    )["n"]
    assert cached == 0, f"cache must be emptied on disconnect, got {cached}"

    # Config-time gate: a skill referencing a tool on the disconnected server
    # is rejected with a readable error (未连接). The source needs a blank
    # line + guidance text so the parser passes and validation reaches the
    # tool check.
    source = (
        f"名称：apitest断链技能{int(time.time())}\n"
        "适用条件：涉及单位换算\n"
        "工具：unit_convert@campus-tools\n"
        "启用：是\n"
        "\n"
        "先让学生自己尝试换算，卡住时再给进率提示。"
    )
    rejected = requests.post(
        f"{ctx['base_url']}/api/skills",
        json={"source": source},
        headers={"Authorization": f"Bearer {ctx['tokens']['teacher']}"},
        timeout=30,
    )
    assert rejected.status_code == 400, (
        f"skill on disconnected server should 400, got {rejected.status_code}: "
        f"{rejected.text[:200]}"
    )
    assert "未连接" in rejected.json()["error"], f"error text {rejected.text[:200]}"


CASE = {
    "name": "教师断开 MCP 服务器（清空缓存；未连接时技能保存被拒）",
    "method": "POST",
    "path": path,
    "role": "teacher",
    "skip_if": skip_if,
    "check": check,
}
