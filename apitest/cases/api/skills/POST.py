"""POST /api/skills — create a skill from a single source text block."""
from helpers import db_query_one

SOURCE = (
    "名称：apitest冒烟技能\n"
    "适用条件：学生在解析几何题目卡住时\n"
    "工具：knowledge_search\n"
    "资料：班级解析几何讲义\n"
    "启用：是\n"
    "\n"
    "先让学生复述题目条件，再逐步追问辅助线思路，不直接给出答案。"
)


def check(resp, ctx):
    assert resp.status_code == 201, f"status {resp.status_code}: {resp.text[:200]}"
    skill = resp.json()["skill"]
    assert skill["name"] == "apitest冒烟技能"
    assert skill["trigger"] == "学生在解析几何题目卡住时"
    assert skill["enabled"] is True
    # DB consistency: the parsed fields landed in the skills table.
    row = db_query_one("SELECT * FROM skills WHERE id = %s", (skill["id"],))
    assert row, "skill row missing"
    assert row["class_id"] == 1 and row["enabled"] == 1
    assert row["description"].startswith("先让学生复述题目条件")
    ctx["skill_id"] = skill["id"]


CASE = {
    "name": "教师按 source 文本新建技能并解析入库",
    "method": "POST",
    "path": "/api/skills",
    "role": "teacher",
    "body": {"source": SOURCE},
    "check": check,
}
