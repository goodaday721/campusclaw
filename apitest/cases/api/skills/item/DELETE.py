"""DELETE /api/skills/{id} — remove the skill created by the POST case."""
from helpers import db_query_one


def path(ctx):
    return f"/api/skills/{ctx['skill_id']}"


def skip_if(ctx):
    return None if ctx.get("skill_id") else "no skill created by the POST case"


def check(resp, ctx):
    assert resp.status_code == 204, f"status {resp.status_code}: {resp.text[:200]}"
    assert resp.text == "", "204 must have an empty body"
    # DB consistency: the row is gone.
    row = db_query_one("SELECT id FROM skills WHERE id = %s", (ctx["skill_id"],))
    assert row is None, "skill row still present after DELETE"
    ctx["skill_id"] = None  # cleanup for any later case


CASE = {
    "name": "教师删除技能并从库中移除",
    "method": "DELETE",
    "path": path,
    "role": "teacher",
    "skip_if": skip_if,
    "check": check,
}
