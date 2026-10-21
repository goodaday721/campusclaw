"""POST /api/mcp/servers — register a server; duplicate name → 409.

Registers a uniquely-named server, asserts the persisted row, then removes it
again so reruns stay idempotent (duplicate-name 409 is asserted against the
freshly created copy, not the seed).
"""
import time

import requests

NAME = f"apitest-tools-{int(time.time())}"
BASE_URL = "http://mcp-demo:8090"
TOKEN = "apitest-plain-token-123"


def check(resp, ctx):
    assert resp.status_code == 201, f"status {resp.status_code}: {resp.text[:200]}"
    server = resp.json()["server"]
    assert server["name"] == NAME
    assert server["baseUrl"] == BASE_URL
    assert server["hasToken"] is True, "registered token must surface as hasToken"
    assert server["status"] == "disconnected"
    assert server["toolsCount"] == 0
    assert '"token"' not in resp.text, "raw token must not appear in the response"

    # DB consistency: the row stores the raw token (server-side only).
    from helpers import db_query_one

    row = db_query_one(
        "SELECT name, base_url, token, status FROM mcp_servers WHERE id = %s",
        (server["id"],),
    )
    assert row, "mcp_servers row missing"
    assert row["token"] == TOKEN and row["status"] == "disconnected"

    # Duplicate name in the same class → 409.
    dup = requests.post(
        f"{ctx['base_url']}/api/mcp/servers",
        json={"name": NAME, "base_url": BASE_URL},
        headers={"Authorization": f"Bearer {ctx['tokens']['teacher']}"},
        timeout=30,
    )
    assert dup.status_code == 409, f"duplicate should 409, got {dup.status_code}"

    # Cleanup so a rerun can register the same fresh name again.
    del_resp = requests.delete(
        f"{ctx['base_url']}/api/mcp/servers/{server['id']}",
        headers={"Authorization": f"Bearer {ctx['tokens']['teacher']}"},
        timeout=30,
    )
    assert del_resp.status_code == 204, f"cleanup DELETE failed: {del_resp.status_code}"
    assert db_query_one("SELECT id FROM mcp_servers WHERE id = %s", (server["id"],)) is None


CASE = {
    "name": "教师登记 MCP 服务器（hasToken 布尔、同名 409、用后清理）",
    "method": "POST",
    "path": "/api/mcp/servers",
    "role": "teacher",
    "body": {"name": NAME, "base_url": BASE_URL, "token": TOKEN},
    "check": check,
}
