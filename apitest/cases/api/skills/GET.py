"""GET /api/skills — list guided skills of the class (teacher sees all)."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    skills = resp.json()["skills"]
    assert isinstance(skills, list) and len(skills) >= 1, "expected the seeded skill"
    assert any(s["name"] == "方程解题引导" for s in skills), "seed skill missing"
    # DB consistency: list length equals the class-1 skill row count.
    row = db_query_one("SELECT COUNT(*) AS n FROM skills WHERE class_id = 1")
    assert row["n"] == len(skills), f"DB {row['n']} != list {len(skills)}"


CASE = {
    "name": "教师查看班级技能列表（含种子技能）",
    "method": "GET",
    "path": "/api/skills",
    "role": "teacher",
    "check": check,
}
