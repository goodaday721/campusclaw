"""POST /api/conversations/{id}/messages — the full lesson-6 chain, end to end.

Preceded by y-setup (skill → agent → conversation) and the connect case. The
student question should make the model propose a unit_convert call; check()
asserts the SSE meta carries the tool_calls verdict BEFORE any delta and that
the audit log row landed.
"""


def body(ctx):
    return {"content": "3千克等于多少克？请调用 unit_convert 工具完成单位换算。"}


def path(ctx):
    return f"/api/conversations/{ctx['mcp_conversation_id']}/messages"


def skip_if(ctx):
    return (
        None if ctx.get("mcp_conversation_id")
        else "no conversation created by the y-setup case"
    )


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:300]}"
    assert resp.headers["Content-Type"].startswith("text/event-stream")

    from helpers import db_query_one, parse_sse

    frames = parse_sse(resp.text)
    kinds = [name for name, _ in frames]
    assert kinds[0] == "meta" and kinds[-1] == "done", f"frame order {kinds}"

    meta = frames[0][1]
    assert meta["status"] == "ok"
    calls = meta.get("tool_calls")
    assert calls, "meta must carry tool_calls before any delta (lesson-6 contract)"
    ok_calls = [c for c in calls
                if c["status"] == "ok" and c["ref"] == "unit_convert@campus-tools"]
    assert ok_calls, f"expected an ok unit_convert call, got {calls}"
    assert all(c["status"] in ("ok", "denied", "error") for c in calls), f"bad statuses {calls}"
    assert all(isinstance(c["round"], int) and c["round"] >= 1 for c in calls), (
        f"bad rounds {calls}"
    )

    answer = "".join(d["text"] for name, d in frames if name == "delta")
    assert answer.strip(), "empty streamed answer"

    # DB consistency: one audit row per ok meta entry, aligned by round.
    from helpers import db_query_all

    rows = db_query_all(
        "SELECT tool_name, server_name, status, round_no, user_id "
        "FROM mcp_call_logs WHERE conversation_id = %s AND status = 'ok' ORDER BY id",
        (ctx["mcp_conversation_id"],),
    )
    assert len(rows) == len(ok_calls), (
        f"audit rows {len(rows)} != ok meta entries {len(ok_calls)}"
    )
    student = db_query_one("SELECT id FROM users WHERE username = 'student_a'")
    assert student, "student_a missing"
    for row, call in zip(rows, ok_calls):
        assert row["tool_name"] == "unit_convert", f"tool_name {row['tool_name']}"
        assert row["server_name"] == "campus-tools", f"server {row['server_name']}"
        assert row["round_no"] == call["round"], (
            f"round {row['round_no']} != meta {call['round']}"
        )
        assert row["user_id"] == student["id"], "audit user mismatch"

    assistant = db_query_one(
        "SELECT content FROM messages WHERE conversation_id = %s AND role = 'assistant' "
        "ORDER BY id DESC LIMIT 1",
        (ctx["mcp_conversation_id"],),
    )
    assert assistant and assistant["content"] == answer, "assistant row differs from stream"


CASE = {
    "name": "全链路：学生提问命中 MCP 工具→meta 先报调用→审计落库",
    "method": "POST",
    "path": path,
    "role": "student",
    "body": body,
    "skip_if": skip_if,
    "sse": True,
    "check": check,
}
