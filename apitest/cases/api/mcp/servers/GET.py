"""GET /api/mcp/servers — teacher lists the class registry (seed pre-registered).

Asserts the token never appears: only a hasToken boolean.
"""
import time


def body(ctx):
    return None


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    servers = resp.json()["servers"]
    assert isinstance(servers, list) and servers, "seeded campus-tools missing"
    # Raw token must not leak anywhere in the response body.
    assert '"token"' not in resp.text and "'token'" not in resp.text, "token leaked!"
    seeded = [s for s in servers if s["name"] == "campus-tools"]
    assert seeded, "seed pre-registered campus-tools not found"
    srv = seeded[0]
    assert srv["hasToken"] is True, "seeded server must have a token"
    assert srv["baseUrl"] == "http://mcp-demo:8090"
    assert srv["status"] in ("connected", "disconnected")
    ctx["mcp_server_id"] = srv["id"]


CASE = {
    "name": "教师列出本班 MCP 服务器（只含 hasToken 布尔值，无令牌原文）",
    "method": "GET",
    "path": "/api/mcp/servers",
    "role": "teacher",
    "check": check,
}
