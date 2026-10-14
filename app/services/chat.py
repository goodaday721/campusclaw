"""Lesson-5 assistant chat pipeline: grounded streaming answers over SSE.

Flow per user message: build the system prompt (agent prompt, falling back to
the class prompt, plus injected enabled skill descriptions and the shared
grounding rules) -> hybrid-retrieve this class's knowledge (optionally
restricted to the agent's bound materials) -> with hits, stream the answer
from the chat gateway; with zero hits, answer the fixed "not found" message
without calling the model. Both turns are persisted AFTER the answer
completes; a mid-stream gateway failure leaves nothing in the database.

The route-facing contract is:
  chat.start(...)      -> validates/retrieves and PRIMES the gateway stream
                          (raises before any byte is streamed, so errors stay
                          plain JSON: AnswerUnavailable -> 503, EmptyQuery -> 400)
  chat.sse_stream(...) -> generator of SSE text: meta -> delta* -> done
"""
import json

from app.db.connection import get_connection
from app.repositories import (
    agents as agents_repo,
    conversations as conversations_repo,
    prompts as prompts_repo,
)
from app.services import model_gateway, retrieval
from app.services.answer import (
    AnswerUnavailable,
    GROUNDING_RULES,
    NO_MATCH_MESSAGE,
    build_sources_message,
)

HISTORY_TURNS = 6  # server-side recent turns injected into the prompt
EXCERPT_LIMIT = 2000  # grounding slices carry real text, not display excerpts


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
    }


def start(
    db: dict,
    qcfg: dict,
    config,
    class_id: int,
    agent: dict,
    conversation_id: int,
    content: str,
) -> dict:
    """Prepare the pipeline and prime the gateway stream.

    Priming (first next()) forces any gateway error BEFORE the SSE response
    starts, so the route can still answer with a normal JSON error.
    """
    prepared = _prepare(db, qcfg, config, class_id, agent, conversation_id, content)
    if prepared["no_match"]:
        return {"prepared": prepared, "gen": None, "first_delta": None}

    user_message = build_sources_message(content, prepared["hits"])
    messages = (
        [{"role": "system", "content": prepared["system"]}]
        + prepared["history"]
        + [{"role": "user", "content": user_message}]
    )
    try:
        gen = model_gateway.chat_stream(config, messages)
        first_delta = next(gen, None)
    except model_gateway.GatewayError as exc:
        raise AnswerUnavailable(str(exc)) from exc
    return {"prepared": prepared, "gen": gen, "first_delta": first_delta}


def sse_event(name: str, data: dict) -> str:
    """Format one SSE frame (event name + JSON data)."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_stream(result: dict, db: dict, conversation_id: int, content: str):
    """Turn the primed stream into SSE frames: meta -> delta* -> done.

    Zero-hit answers reuse the fixed message and never touch the gateway.
    A mid-stream gateway failure yields no `done` frame (the client shows an
    interrupted answer) and persists nothing.
    """
    prepared = result["prepared"]
    yield sse_event("meta", {"status": "ok", "citations": prepared["citations"]})

    if prepared["no_match"]:
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
