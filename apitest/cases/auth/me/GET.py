"""GET /auth/me — current user identity from the Bearer token."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    user = resp.json()["user"]
    assert user["role"] == "teacher"
    # DB consistency: the identity matches the users table row (username is
    # resolved server-side; the response only carries id/role/classId).
    row = db_query_one(
        "SELECT id, class_id FROM users WHERE username = %s", ("teacher_a",)
    )
    assert row and row["id"] == user["userId"] and row["class_id"] == user["classId"]


CASE = {
    "name": "携带 token 查询当前用户身份",
    "method": "GET",
    "path": "/auth/me",
    "role": "teacher",
    "check": check,
}
