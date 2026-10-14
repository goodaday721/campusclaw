"""GET /api/conversations — the caller's conversation list (newest first)."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    conversations = resp.json()["conversations"]
    assert isinstance(conversations, list)
    for conv in conversations:
        assert "id" in conv and "agentId" in conv and "agentName" in conv
    # DB consistency: row count for student_a in class 1 matches the list.
    row = db_query_one(
        "SELECT COUNT(*) AS n FROM conversations c JOIN users u ON u.id = c.user_id "
        "WHERE u.username = 'student_a' AND c.class_id = 1"
    )
    assert row["n"] == len(conversations), f"DB {row['n']} != list {len(conversations)}"


CASE = {
    "name": "学生查看自己的会话列表",
    "method": "GET",
    "path": "/api/conversations",
    "role": "student",
    "check": check,
}
