"""Unauthenticated access to assignments must be 401."""


def check(resp, ctx):
    assert resp.status_code == 401, f"status {resp.status_code}: {resp.text[:200]}"
    assert "error" in resp.json()


CASE = {
    "name": "未登录访问作业接口被拒（401）",
    "method": "GET",
    "path": "/api/assignments",
    "check": check,
}
