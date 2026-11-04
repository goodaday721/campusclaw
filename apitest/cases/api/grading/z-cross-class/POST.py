"""B-class student submits to an A-class assignment → isomorphic 404."""
import requests


def path(ctx):
    return f"/api/assignments/{ctx['grading_assignment_id']}/submissions"


def skip_if(ctx):
    return None if ctx.get("grading_assignment_id") else "no assignment from a-setup"


def check(resp, ctx):
    # The case's own request (A-class student → A-class assignment) is legal.
    assert resp.status_code == 202, f"status {resp.status_code}: {resp.text[:200]}"

    # Login as student_b and hit the same URL: cross-class must be identical 404.
    login = requests.post(
        f"{ctx['base_url']}/auth/login",
        json={"username": "student_b", "password": "student_b_pass"},
        timeout=30,
    )
    login.raise_for_status()
    other = requests.post(
        f"{ctx['base_url']}{path(ctx)}",
        json={"answer": "x = 4"},
        headers={"Authorization": f"Bearer {login.json()['token']}"},
        timeout=60,
    )
    assert other.status_code == 404, other.text[:200]
    assert other.json()["error"] == "not found"


CASE = {
    "name": "同班提交 202 / 跨班提交同构 404（B 班学生看不到 A 班作业）",
    "method": "POST",
    "path": path,
    "role": "student",
    "body": {"answer": "x = 4"},
    "skip_if": skip_if,
    "check": check,
}
