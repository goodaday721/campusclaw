"""Lesson-5 assistant chat pipeline: grounded streaming answers over SSE.

Flow per user message: build the system prompt (agent prompt, falling back to
the class prompt, plus injected enabled skill descriptions and the shared
grounding rules) -> hybrid-retrieve this class's knowledge (optionally
restricted to the agent's bound materials) -> with hits, stream the answer
from the chat gateway; with zero hits and no MCP tool references, answer the
fixed "not found" message without calling the model. Zero hits WITH tool
references still run the tool loop first: successful tool data counts as
grounding and unlocks a streaming answer, otherwise the fixed message stays.
Both turns are persisted AFTER the answer
completes; a mid-stream gateway failure leaves nothing in the database.

Lesson 6 adds the MCP tool loop: when the turn's skills reference MCP tools
("tool@server"), the resolved candidate set is sent to the model as tool
declarations; each proposed call is executed BY THE HOST (schema check, the
server's own bearer token, an audit row), the sanitized result text is
appended to the user message as DATA (never instructions), and the loop runs
at most max_rounds turns / max_calls cumulative executions before degrading
gracefully. The final answer is then streamed WITHOUT tool declarations, so
tool_calls metadata is complete before the first delta — the SSE sequence
stays meta -> delta* -> done.

The route-facing contract is:
  chat.start(...)      -> validates/retrieves, runs the tool loop and PRIMES
                          the gateway stream (raises before any byte is
                          streamed, so errors stay plain JSON)
  chat.sse_stream(...) -> generator of SSE text: meta -> delta* -> done
"""
import json

from app.db.connection import get_connection
from app.repositories import (
    agents as agents_repo,
    conversations as conversations_repo,
    mcp as mcp_repo,
    prompts as prompts_repo,
)
from app.services import mcp_client, model_gateway, mcp_service, retrieval
from app.services.answer import (
    AnswerUnavailable,
    GROUNDING_RULES,
    NO_MATCH_MESSAGE,
    build_sources_message,
)
from app.services.mcp_client import McpError

HISTORY_TURNS = 6  # server-side recent turns injected into the prompt
EXCERPT_LIMIT = 2000  # grounding slices carry real text, not display excerpts
TOOL_TEXT_SUMMARY = 120  # meta.tool_calls text summary length

# Lesson 11 拓展：关怀式对话。该技能只在学生表达挫败/焦虑时注入，避免
# 每次回答都被关怀话术污染；命中后即使检索零命中也会调用模型（否则会被
# 「资料中未找到」的固定文案吞掉，正好在最需要安抚时最冷漠）。
CARE_SKILL_NAME = "关怀式对话"
CARE_PATTERNS = (
    "不会", "听不懂", "看不懂", "学不会", "太难", "好难", "崩溃", "焦虑",
    "不想学", "想放弃", "放弃", "压力", "害怕", "没信心", "学不下去",
)


def needs_care(text: str) -> bool:
    """True when the student's message signals frustration or anxiety."""
    if not text:
        return False
    return any(p in text for p in CARE_PATTERNS)


def _prepare(
    db: dict,
    qcfg: dict,
    config,
    class_id: int,
    agent: dict,
    conversation_id: int,
    content: str,
) -> dict:
    """Resolve prompt/skills/materials, retrieve evidence, build citations.

    Raises retrieval.EmptyQuery (400) and AnswerUnavailable (503).
    """
    conn = get_connection(db)
    try:
        agent_prompt = (agent.get("prompt") or "").strip()
        class_prompt = prompts_repo.get(conn, class_id) or ""
        system_prompt = agent_prompt or class_prompt
        skills = agents_repo.skills_for_agent(conn, agent["id"])
        material_ids = set(agents_repo.material_ids_for_agent(conn, agent["id"]))
        history = conversations_repo.recent_messages(
            conn, conversation_id, limit=HISTORY_TURNS
        )
    finally:
        conn.close()

    # 关怀式对话只在命中挫败/焦虑信号时注入；其余技能始终注入。
    care = needs_care(content)
    skills = [s for s in skills if s["name"] != CARE_SKILL_NAME or care]

    parts = [system_prompt] if system_prompt.strip() else []
    for skill in skills:
        parts.append(f"【技能：{skill['name']}】\n{skill['description']}")
    parts.append(GROUNDING_RULES)
    system = "\n\n".join(parts)

    try:
        hits = retrieval.search(
            db,
            qcfg,
            config,
            class_id,
            content,
            mode=retrieval.HYBRID,
            final_limit=config.ask_top_k,
            excerpt_limit=EXCERPT_LIMIT,
        )
    except retrieval.RetrievalUnavailable as exc:
        raise AnswerUnavailable(str(exc)) from exc

    if material_ids:
        # The agent is restricted to its bound materials; retrieval stays
        # class-wide, so filter the assembled hits afterwards.
        hits = [h for h in hits if h["materialId"] in material_ids]

    citations = [
        {
            "ref": idx,
            "materialId": hit["materialId"],
            "materialTitle": hit["materialTitle"],
            "chunkIndex": hit["chunkIndex"],
            "materialUrl": hit["materialUrl"],
        }
        for idx, hit in enumerate(hits, start=1)
    ]

    return {
        "system": system,
        "history": history,
        "hits": hits,
        "citations": citations,
        "skill_name": ("、".join(s["name"] for s in skills) if skills else None),
        "no_match": not hits,
        "care": care,
        "skill_refs": [
            t for s in skills for t in (s.get("tools") or [])
            if mcp_service.parse_reference(t) is not None
        ],
    }


def _schema_ok(arguments: dict, schema: dict) -> bool:
    """Light host-side parameter check against the discovered inputSchema:
    required fields present + basic types. The same structure the model used
    to fill the arguments is used once more to validate them."""
    if not isinstance(arguments, dict):
        return False
    if not schema or not isinstance(schema, dict):
        return True
    for key in schema.get("required") or []:
        if key not in arguments or arguments[key] is None:
            return False
    props = schema.get("properties") or {}
    types = {"string": str, "number": (int, float), "integer": int,
             "boolean": bool, "array": list, "object": dict}
    for key, value in arguments.items():
        expected = ((props.get(key) or {}).get("type"))
        cls = types.get(expected)
        if cls and not isinstance(value, cls):
            return False
    return True


def _execute_call(conn, config, class_id: int, user_id: int, conversation_id: int,
                  call: dict, candidate: dict | None, round_no: int) -> dict:
    """Execute one proposed tool call as the host: re-check availability,
    validate parameters, call with the server's own token, audit the outcome.
    Returns the meta entry {ref, status, text, round}."""
    tool_name = call["name"]
    if candidate is None:
        # Not in this turn's candidate set (hallucinated or connection lost
        # before declarations were built). Attribute it only when some
        # connected server of this class lists the tool; otherwise the
        # failure has no attributable server and leaves NO audit row.
        meta = {"ref": tool_name, "status": "denied", "text": "该工具不在本次可用候选集内",
                "round": round_no}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, s.name FROM mcp_servers s JOIN mcp_tools_cache c "
                "ON c.server_id = s.id WHERE s.class_id = %s AND s.status = 'connected' "
                "AND c.name = %s LIMIT 1",
                (class_id, tool_name),
            )
            row = cur.fetchone()
        if row:
            mcp_repo.append_call(
                conn, class_id, row["id"], row["name"], tool_name, "denied",
                "工具不在本次可用候选集内", user_id, conversation_id, round_no,
            )
            conn.commit()
            meta["ref"] = f"{tool_name}@{row['name']}"
        return meta

    ref = candidate["ref"]
    server = mcp_repo.find(conn, candidate["server_id"], class_id)
    if server is None:
        # Server deleted between discovery and execution: unattributable.
        return {"ref": ref, "status": "denied", "text": "服务器已不存在", "round": round_no}
    if server["status"] != "connected" or not mcp_repo.tool_exists(
        conn, server["id"], tool_name
    ):
        mcp_repo.append_call(
            conn, class_id, server["id"], server["name"], tool_name, "denied",
            "服务器未连接或工具不在最近发现清单中", user_id, conversation_id, round_no,
        )
        conn.commit()
        return {"ref": ref, "status": "denied",
                "text": "服务器未连接或工具不在最近发现清单中", "round": round_no}

    if not _schema_ok(call["arguments"], candidate["input_schema"]):
        mcp_repo.append_call(
            conn, class_id, server["id"], server["name"], tool_name, "denied",
            "参数未通过工具声明的结构校验", user_id, conversation_id, round_no,
        )
        conn.commit()
        return {"ref": ref, "status": "denied", "text": "参数未通过工具声明的结构校验",
                "round": round_no}

    try:
        text = mcp_client.call_tool(
            candidate["base_url"], candidate["token"], tool_name,
            call["arguments"], config,
        )
    except McpError as exc:
        reason = str(exc)
        mcp_repo.append_call(
            conn, class_id, server["id"], server["name"], tool_name, "error",
            reason, user_id, conversation_id, round_no,
        )
        conn.commit()
        return {"ref": ref, "status": "error", "text": reason, "round": round_no}

    safe_text = mcp_service.sanitize_tool_text(text)
    mcp_repo.append_call(
        conn, class_id, server["id"], server["name"], tool_name, "ok",
        safe_text[:200], user_id, conversation_id, round_no,
    )
    conn.commit()
    return {"ref": ref, "status": "ok", "text": safe_text[:TOOL_TEXT_SUMMARY],
            "round": round_no}


def _data_segment(meta: dict) -> str:
    """Tool outcome as a DATA segment in the user message (never the system
    prompt, never phrased as an instruction)."""
    if meta["status"] == "ok":
        return f"[工具 {meta['ref']} 第{meta['round']}轮返回的数据]\n{meta['text']}"
    return f"[工具 {meta['ref']} 第{meta['round']}轮调用失败：{meta['text']}]"


TOOL_DATA_NOTE = (
    "本轮对话已经执行过外部工具：用户消息中以「[工具 … 返回的数据]」标注的内容"
    "是工具的返回结果，与资料切片同为可靠依据，且优先级更高。只要工具数据已包含"
    "回答问题所需的信息，就必须直接依据它作答（例如给出换算数值与进率），"
    f"不得回答“{NO_MATCH_MESSAGE}”，也不要因为资料切片与本问题无关而拒答。"
    "标注为「调用失败」的部分表示该数据本次不可用，不要编造。"
    "回答里不要复述「[工具 … 返回的数据]」这类标注字样。"
)


def _run_tool_loop(db: dict, config, class_id: int, user_id: int,
                   conversation_id: int, messages: list[dict],
                   candidates: dict) -> list[dict]:
    """Run the host-executed tool loop; returns meta entries for SSE.

    Gates: config.mcp_max_rounds turns, config.mcp_max_calls cumulative
    executions. Over the limit the loop simply stops calling and the final
    streaming turn answers from what has been gathered (graceful degradation).
    """
    metas: list[dict] = []
    calls_used = 0
    conn = get_connection(db)
    try:
        for round_no in range(1, config.mcp_max_rounds + 1):
            if calls_used >= config.mcp_max_calls:
                break
            response = model_gateway.chat_with_tools(
                config, messages, candidates["declarations"]
            )
            calls = response["tool_calls"]
            if not calls:
                break  # the model is done proposing; final turn streams
            for call in calls:
                if calls_used >= config.mcp_max_calls:
                    break
                candidate = candidates["by_tool"].get(call["name"])
                meta = _execute_call(
                    conn, config, class_id, user_id, conversation_id,
                    call, candidate, round_no,
                )
                metas.append(meta)
                calls_used += 1
                # Append the outcome as DATA to the user message so the next
                # round (and the streaming close) sees it.
                messages[-1]["content"] += "\n\n" + _data_segment(meta)
        return metas
    finally:
        conn.close()


def start(
    db: dict,
    qcfg: dict,
    config,
    class_id: int,
    agent: dict,
    conversation_id: int,
    content: str,
    user_id: int | None = None,
) -> dict:
    """Prepare the pipeline, run the tool loop and prime the gateway stream.

    Priming (first next()) forces any gateway error BEFORE the SSE response
    starts, so the route can still answer with a normal JSON error.
    """
    prepared = _prepare(db, qcfg, config, class_id, agent, conversation_id, content)
    # Zero hits short-circuit ONLY when the turn's skills reference no MCP
    # tools: otherwise the tool loop still runs and successful tool data can
    # ground the answer even without any retrieval slice.
    if prepared["no_match"] and not prepared["skill_refs"] and not prepared["care"]:
        return {"prepared": prepared, "gen": None, "first_delta": None,
                "tool_calls_meta": []}

    user_message = build_sources_message(content, prepared["hits"])
    messages = (
        [{"role": "system", "content": prepared["system"]}]
        + prepared["history"]
        + [{"role": "user", "content": user_message}]
    )

    # Lesson 6: resolve MCP references into the turn's candidate set and run
    # the host-executed loop BEFORE streaming. Every proposed call has been
    # executed and audited by the time the first delta is emitted, so
    # tool_calls can ride in the meta event ahead of the text.
    tool_calls_meta: list[dict] = []
    conn = get_connection(db)
    try:
        candidates = mcp_service.build_candidates(
            conn, class_id, prepared["skill_refs"]
        ) if prepared["skill_refs"] else {"declarations": [], "by_tool": {}, "unresolved": []}
        # Runtime re-check failures (disconnected / not in the latest
        # discovery): record denied when attributable, surface in meta —
        # never silently dropped (TOCTOU is disclosed, not hidden).
        for item in candidates.get("unresolved") or []:
            reason = "服务器未连接或工具不在最近发现清单中"
            if item["server_id"] is not None:
                mcp_repo.append_call(
                    conn, class_id, item["server_id"], item["server_name"],
                    item["ref"].split("@", 1)[0], "denied", reason,
                    user_id if user_id is not None else agent["id"],
                    conversation_id, 1,
                )
                conn.commit()
            tool_calls_meta.append({
                "ref": item["ref"], "status": "denied",
                "text": reason if item["server_id"] is not None else "服务器已不存在",
                "round": 1,
            })
            # Tell the model this tool failed, as data — never silently.
            messages[-1]["content"] += "\n\n" + _data_segment(tool_calls_meta[-1])
    finally:
        conn.close()
    if candidates["declarations"]:
        tool_calls_meta += _run_tool_loop(
            db, config, class_id, user_id if user_id is not None else agent["id"],
            conversation_id, messages, candidates,
        )
        if any(m["status"] == "ok" for m in tool_calls_meta):
            # Tool data entered the user message; tell the model these
            # segments count as reliable grounding like the slices do.
            messages[0]["content"] += "\n" + TOOL_DATA_NOTE

    # Zero hits with no successful tool data: no evidence at all (neither
    # slices nor tool results) -> fixed message, gateway untouched. Failed
    # attempts still ride home in tool_calls_meta so the SSE meta discloses
    # them ahead of the fixed text. A care turn is exempt: at that moment a
    # comforting reply beats a clinically correct "not found".
    if (prepared["no_match"] and not prepared["care"]
            and not any(m["status"] == "ok" for m in tool_calls_meta)):
        return {"prepared": prepared, "gen": None, "first_delta": None,
                "tool_calls_meta": tool_calls_meta}

    try:
        gen = model_gateway.chat_stream(config, messages)
        first_delta = next(gen, None)
    except model_gateway.GatewayError as exc:
        raise AnswerUnavailable(str(exc)) from exc
    return {"prepared": prepared, "gen": gen, "first_delta": first_delta,
            "tool_calls_meta": tool_calls_meta}


def sse_event(name: str, data: dict) -> str:
    """Format one SSE frame (event name + JSON data)."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_stream(result: dict, db: dict, conversation_id: int, content: str):
    """Turn the primed stream into SSE frames: meta -> delta* -> done.

    A primed stream of None (zero hits with no grounding left after the tool
    loop) reuses the fixed message and never touches the gateway; any failed
    tool attempts were already disclosed in the meta event. A mid-stream
    gateway failure yields no `done` frame (the client shows an interrupted
    answer) and persists nothing.
    """
    prepared = result["prepared"]
    meta_payload = {"status": "ok", "citations": prepared["citations"]}
    if result.get("tool_calls_meta"):
        # Only when this turn really called tools; absent key otherwise, and
        # always ahead of every delta.
        meta_payload["tool_calls"] = result["tool_calls_meta"]
    yield sse_event("meta", meta_payload)

    if result["gen"] is None:
        answer_text = NO_MATCH_MESSAGE
        yield sse_event("delta", {"text": answer_text})
        message_id = _persist(db, conversation_id, content, answer_text, [], None)
        yield sse_event("done", {"message_id": message_id})
        return

    parts = [result["first_delta"]] if result["first_delta"] else []
    if result["first_delta"]:
        yield sse_event("delta", {"text": result["first_delta"]})
    try:
        for delta in result["gen"]:
            parts.append(delta)
            yield sse_event("delta", {"text": delta})
    except model_gateway.GatewayError:
        # Stream broke after deltas were already sent; nothing is persisted
        # and the missing `done` tells the client the answer was interrupted.
        return

    answer_text = "".join(parts)
    if not answer_text.strip():
        return  # empty generation -> treat as interrupted; nothing persisted
    message_id = _persist(
        db,
        conversation_id,
        content,
        answer_text,
        prepared["citations"],
        prepared["skill_name"],
    )
    yield sse_event("done", {"message_id": message_id})


def _persist(
    db: dict,
    conversation_id: int,
    content: str,
    answer_text: str,
    citations: list,
    skill_name: str | None,
) -> int:
    """Append the user turn and the finished assistant turn (single commit)."""
    conn = get_connection(db)
    try:
        conversations_repo.append_message(conn, conversation_id, "user", content)
        message_id = conversations_repo.append_message(
            conn,
            conversation_id,
            "assistant",
            answer_text,
            citations=citations,
            skill_name=skill_name,
        )
        conn.commit()
        return message_id
    finally:
        conn.close()
