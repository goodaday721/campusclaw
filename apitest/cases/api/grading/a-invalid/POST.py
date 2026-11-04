"""Missing required fields must be rejected with 400."""


def check(resp, ctx):
    assert resp.status_code == 400, f"status {resp.status_code}: {resp.text[:200]}"
    assert "error" in resp.json()


CASE = {
    "name": "创建作业缺必填字段被拒（400）",
    "method": "POST",
    "path": "/api/assignments",
    "role": "teacher",
    "body": {"title": "只有标题"},
    "check": check,
}
