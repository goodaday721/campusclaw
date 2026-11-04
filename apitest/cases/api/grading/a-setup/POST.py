"""Setup: teacher creates one assignment so later cases can submit against it.

A uniquely titled assignment is created per run; the id lands in ctx.
"""
import time

TITLE = f"apitest-作业-{int(time.time())}"


def check(resp, ctx):
    assert resp.status_code == 201, f"status {resp.status_code}: {resp.text[:200]}"
    assignment = resp.json()["assignment"]
    assert assignment["title"] == TITLE
    assert assignment["classId"] == 1

    from helpers import db_query_one

    row = db_query_one(
        "SELECT class_id, title, reference_answer FROM assignments WHERE id = %s",
        (assignment["id"],),
    )
    assert row, "assignments row missing"
    assert row["class_id"] == 1 and row["title"] == assignment["title"]
    ctx["grading_assignment_id"] = assignment["id"]


CASE = {
    "name": "教师创建作业（201、班级归属、参考答案落库）",
    "method": "POST",
    "path": "/api/assignments",
    "role": "teacher",
    "body": {
        "title": TITLE,
        "question": "解方程 2x + 3 = 11",
        "reference_answer": "x = 4",
    },
    "check": check,
}
