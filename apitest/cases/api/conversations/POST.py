"""POST /api/conversations — create a conversation bound to a class agent."""
from helpers import db_query_one


def body(ctx):
    return {"agent_id": ctx["agent_id"]}


def skip_if(ctx):
    return None if ctx.get("agent_id") else "no agent discovered by the GET case"


def check(resp, ctx):
    assert resp.status_code == 201, f"status {resp.status_code}: {resp.text[:200]}"
    conv = resp.json()["conversation"]
    assert isinstance(conv["id"], int)
    assert conv["agentId"] == ctx["agent_id"]
    assert conv["title"] == ""
    # DB consistency: the row exists for student_a in class 1 with that agent.
    row = db_query_one(
        "SELECT c.id, c.agent_id, c.class_id FROM conversations c "
        "JOIN users u ON u.id = c.user_id "
        "WHERE c.id = %s AND u.username = 'student_a'",
        (conv["id"],),
    )
    assert row, "conversation row missing"
    assert row["agent_id"] == ctx["agent_id"] and row["class_id"] == 1
    ctx["conversation_id"] = conv["id"]


CASE = {
    "name": "学生在解题助手下新建会话",
    "method": "POST",
    "path": "/api/conversations",
    "role": "student",
    "body": body,
    "skip_if": skip_if,
    "check": check,
}
