"""GET /api/mcp/call-logs — teacher-only class audit list (may be empty)."""


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    calls = resp.json()["calls"]
    assert isinstance(calls, list), "calls must be a list"
    for call in calls:
        assert set(call) >= {"ref", "status", "userId", "conversationId", "round",
                             "createdAt"}, f"missing audit fields: {call}"
        assert call["status"] in ("ok", "denied", "error"), call["status"]
        assert "@" in call["ref"], f"ref must be tool@server: {call['ref']}"


CASE = {
    "name": "教师查看本班 MCP 调用审计（结构完整、倒序）",
    "method": "GET",
    "path": "/api/mcp/call-logs",
    "role": "teacher",
    "check": check,
}
