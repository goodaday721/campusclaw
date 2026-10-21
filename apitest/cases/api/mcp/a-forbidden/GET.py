"""GET /api/mcp/servers as a student — must be 403 (teacher-only)."""


def check(resp, ctx):
    assert resp.status_code == 403, f"status {resp.status_code}: {resp.text[:200]}"
    assert "servers" not in resp.json(), "must not leak server list to students"


CASE = {
    "name": "学生访问 MCP 管理接口被拒（403）",
    "method": "GET",
    "path": "/api/mcp/servers",
    "role": "student",
    "check": check,
}
