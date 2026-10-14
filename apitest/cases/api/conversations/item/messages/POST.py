"""POST /api/conversations/{id}/messages — SSE streamed grounded answer."""
from helpers import db_query_one, parse_sse


def body(ctx):
    # Remember the transcript size so check() can assert exactly 2 new rows.
    row = db_query_one(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = %s",
        (ctx["conversation_id"],),
    )
    ctx["msg_before"] = row["n"]
    return {"content": "服务端会话 是什么？"}


def path(ctx):
    return f"/api/conversations/{ctx['conversation_id']}/messages"


def skip_if(ctx):
    return None if ctx.get("conversation_id") else "no conversation created yet"


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    assert resp.headers["Content-Type"].startswith(
        "text/event-stream"
    ), f"content-type {resp.headers['Content-Type']}"

    frames = parse_sse(resp.text)
    kinds = [name for name, _ in frames]
    assert kinds[0] == "meta" and kinds[-1] == "done", f"frame order {kinds}"
    assert all(k == "delta" for k in kinds[1:-1]), f"unexpected frames {kinds}"

    meta = frames[0][1]
    assert meta["status"] == "ok"
    assert len(meta["citations"]) >= 1, "expected grounded citations in meta"
    answer = "".join(d["text"] for name, d in frames if name == "delta")
    assert answer.strip(), "empty streamed answer"

    # DB consistency: user + assistant rows appended; assistant carries
    # citations and the injected skill name.
    after = db_query_one(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = %s",
        (ctx["conversation_id"],),
    )["n"]
    assert after == ctx["msg_before"] + 2, f"expected +2 rows, got {after}"

    user_row = db_query_one(
        "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' "
        "ORDER BY id DESC LIMIT 1",
        (ctx["conversation_id"],),
    )
    assert user_row["content"] == "服务端会话 是什么？"

    assistant_row = db_query_one(
        "SELECT content, citations, skill_name FROM messages "
        "WHERE conversation_id = %s AND role = 'assistant' ORDER BY id DESC LIMIT 1",
        (ctx["conversation_id"],),
    )
    assert assistant_row["content"] == answer, "assistant row differs from stream"
    import json

    citations = json.loads(assistant_row["citations"])
    assert len(citations) >= 1, "assistant citations not persisted"
    assert assistant_row["skill_name"], "skill_name not persisted"


CASE = {
    "name": "学生提问获得 SSE 流式带引用回答并落库",
    "method": "POST",
    "path": path,
    "role": "student",
    "body": body,
    "skip_if": skip_if,
    "sse": True,
    "check": check,
}
