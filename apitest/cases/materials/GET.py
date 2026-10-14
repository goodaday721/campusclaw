"""GET /materials — list materials scoped to the caller's class."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data["classId"] == 1
    materials = data["materials"]
    assert len(materials) >= 1, "expected seeded materials"
    # DB consistency: list length equals the class-1 material row count.
    row = db_query_one("SELECT COUNT(*) AS n FROM materials WHERE class_id = 1")
    assert row["n"] == len(materials), f"DB {row['n']} != list {len(materials)}"


CASE = {
    "name": "材料列表按班级隔离返回",
    "method": "GET",
    "path": "/materials",
    "role": "teacher",
    "check": check,
}
