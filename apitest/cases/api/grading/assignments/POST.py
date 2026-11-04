"""Students must not create assignments (403, no row written)."""


def check(resp, ctx):
    assert resp.status_code == 403, f"status {resp.status_code}: {resp.text[:200]}"
    from helpers import db_query_one

    assert db_query_one(
        "SELECT count(*) AS n FROM assignments WHERE title = 'student-forbidden'"
    )["n"] == 0


CASE = {
    "name": "学生创建作业被拒（403、不落库）",
    "method": "POST",
    "path": "/api/assignments",
    "role": "student",
    "body": {
        "title": "student-forbidden",
        "question": "不该存在",
        "reference_answer": "不该存在",
    },
    "check": check,
}
