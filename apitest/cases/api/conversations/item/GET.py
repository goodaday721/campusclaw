"""GET /api/conversations/{id} — conversation detail with its messages."""
from helpers import db_query_one


def path(ctx):
    return f"/api/conversations/{ctx['conversation_id']}"


def skip_if(ctx):
    return None if ctx.get("conversation_id") else "no conversation created yet"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data["conversation"]["id"] == ctx["conversation_id"]
    assert isinstance(data["messages"], list)
    # DB consistency: stored message count equals the returned list length.
    row = db_query_one(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = %s",
        (ctx["conversation_id"],),
    )
    assert row["n"] == len(data["messages"]), (
        f"DB {row['n']} != list {len(data['messages'])}"
    )


CASE = {
    "name": "学生查看会话详情与历史消息",
    "method": "GET",
    "path": path,
    "role": "student",
    "skip_if": skip_if,
    "check": check,
}
