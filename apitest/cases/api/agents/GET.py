"""GET /api/agents — student sees enabled agents of the class."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    agents = resp.json()["agents"]
    assert len(agents) >= 1, "expected the seeded 解题助手 agent"
    agent = agents[0]
    assert agent["enabled"] is True
    # DB consistency: enabled agent rows for class 1 match the list length.
    row = db_query_one(
        "SELECT COUNT(*) AS n FROM agents WHERE class_id = 1 AND enabled = 1"
    )
    assert row["n"] == len(agents), f"DB {row['n']} != list {len(agents)}"
    ctx["agent_id"] = agent["id"]


CASE = {
    "name": "学生查看班级可用智能体（种子解题助手）",
    "method": "GET",
    "path": "/api/agents",
    "role": "student",
    "check": check,
}
