"""POST /auth/login — issue a JWT for valid credentials."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data.get("token"), "token missing in response"
    assert data["user"]["role"] == "teacher"
    assert data["user"]["classId"] == 1
    # DB consistency: the user row exists with the expected role/class.
    row = db_query_one(
        "SELECT id, role, class_id FROM users WHERE username = %s", ("teacher_a",)
    )
    assert row and row["role"] == "teacher" and row["class_id"] == 1


CASE = {
    "name": "登录成功返回 token 与用户信息（teacher_a）",
    "method": "POST",
    "path": "/auth/login",
    "role": None,
    "body": {"username": "teacher_a", "password": "teacher_a_pass"},
    "check": check,
}
