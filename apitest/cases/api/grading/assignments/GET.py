"""Teacher lists class assignments; the setup case's assignment is present."""


def skip_if(ctx):
    return None if ctx.get("grading_assignment_id") else "no assignment from a-setup"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    rows = resp.json()["assignments"]
    assert isinstance(rows, list) and rows, "assignment list empty"
    assert all(a["classId"] == 1 for a in rows), "cross-class assignment leaked"
    assert any(a["id"] == ctx["grading_assignment_id"] for a in rows), "setup missing"


CASE = {
    "name": "教师列出本班作业（只含本班、含 setup 作业）",
    "method": "GET",
    "path": "/api/assignments",
    "role": "teacher",
    "skip_if": skip_if,
    "check": check,
}
