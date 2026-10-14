"""GET /api/prompt — read the class-level system prompt."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data["classId"] == 1
    assert isinstance(data["body"], str) and data["body"].strip(), "empty prompt"
    # DB consistency: the stored row matches the response body.
    row = db_query_one("SELECT body FROM class_prompts WHERE class_id = 1")
    assert row and row["body"] == data["body"]
    # Remember for the PUT case so it rewrites the same value (non-destructive).
    ctx["prompt_body"] = data["body"]


CASE = {
    "name": "读取班级系统提示词",
    "method": "GET",
    "path": "/api/prompt",
    "role": "student",
    "check": check,
}
