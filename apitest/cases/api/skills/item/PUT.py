"""PUT /api/skills/{id} — update a skill (here: disable it)."""
from helpers import db_query_one

UPDATED_SOURCE = (
    "名称：apitest冒烟技能（改）\n"
    "适用条件：学生请求直接答案时\n"
    "工具：knowledge_search\n"
    "资料：班级解析几何讲义\n"
    "启用：否\n"
    "\n"
    "关闭状态下不注入回答；引导学生先自己尝试一步。"
)


def path(ctx):
    return f"/api/skills/{ctx['skill_id']}"


def skip_if(ctx):
    return None if ctx.get("skill_id") else "no skill created by the POST case"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    skill = resp.json()["skill"]
    assert skill["name"] == "apitest冒烟技能（改）"
    assert skill["enabled"] is False
    # DB consistency: name + enabled flag updated in the row.
    row = db_query_one(
        "SELECT name, enabled FROM skills WHERE id = %s", (ctx["skill_id"],)
    )
    assert row and row["name"] == "apitest冒烟技能（改）" and row["enabled"] == 0


CASE = {
    "name": "教师更新技能（改名并停用）",
    "method": "PUT",
    "path": path,
    "role": "teacher",
    "body": {"source": UPDATED_SOURCE},
    "skip_if": skip_if,
    "check": check,
}
