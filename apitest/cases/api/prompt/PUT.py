"""PUT /api/prompt — teacher updates the class system prompt (upsert)."""

DEFAULT_PROMPT = "A班默认提示词（apitest 回写校验）"


def body(ctx):
    # Rewrite the value read by the GET case: exercises the write path while
    # keeping the shared environment unchanged.
    return {"body": ctx.get("prompt_body") or DEFAULT_PROMPT}


def check(resp, ctx):
    from helpers import db_query_one

    sent = ctx.get("prompt_body") or DEFAULT_PROMPT
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data["body"] == sent
    # DB consistency: the upserted row matches what we sent.
    row = db_query_one("SELECT body FROM class_prompts WHERE class_id = 1")
    assert row and row["body"] == sent, "class_prompts row not updated"


CASE = {
    "name": "教师更新班级提示词并落库",
    "method": "PUT",
    "path": "/api/prompt",
    "role": "teacher",
    "body": body,
    "check": check,
}
