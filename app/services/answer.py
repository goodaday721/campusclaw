"""Grounded question answering: retrieve first, generate only with evidence.

POST /ask flow: hybrid search within the session class, take top-K chunks.
Zero hits -> fixed message + empty citations, and the chat gateway is NOT
called. With hits, a server-built prompt (titles, chunk indexes, chunk text,
the user question and optional prior turns) is sent to the chat gateway; the
answer must cite [1][2]... in the same order as the citations list. Client
system messages are dropped; vectors and raw gateway payloads are never passed.
"""
from app.services import model_gateway, retrieval

NO_MATCH_MESSAGE = retrieval.NO_MATCH_MESSAGE

_SYSTEM_PROMPT = (
    "你是班级课程资料问答助手。你只能依据下面提供的本班资料切片回答问题，"
    "不得使用切片之外的任何知识。每条结论后用 [序号] 标注其出处，"
    "序号必须与给出的资料编号一致。若资料不足以回答问题，"
    f"直接回答“{NO_MATCH_MESSAGE}”。回答使用简体中文，保持简短。"
)


class AnswerUnavailable(Exception):
    """Chat/retrieval dependency unavailable → 503."""


def _sanitize_history(history) -> list[dict]:
    """Keep only plain user/assistant turns; any client system role is dropped."""
    cleaned: list[dict] = []
    if not isinstance(history, list):
        return cleaned
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content})
    return cleaned[-6:]  # bound context: at most the last few turns


def _build_sources_message(question: str, hits: list[dict]) -> str:
    lines = ["资料切片："]
    for idx, hit in enumerate(hits, start=1):
        lines.append(
            f"[{idx}] 材料《{hit['materialTitle']}》切片{hit['chunkIndex']}：\n"
            f"{hit['excerpt']}"
        )
    lines.append(f"\n问题：{question}")
    return "\n".join(lines)


def build_answer(
    db: dict, qcfg: dict, config, class_id: int, question: str, history=None
) -> dict:
    """Return {"answer": str, "citations": [...]} (chat gateway only on hits)."""
    try:
        hits = retrieval.search(
            db,
            qcfg,
            config,
            class_id,
            question,
            mode=retrieval.HYBRID,
            final_limit=config.ask_top_k,
            # Grounding prompts need the real chunk text, not the 200-char
            # search-result excerpt, or the model refuse on truncated evidence.
            excerpt_limit=2000,
        )
    except retrieval.RetrievalUnavailable as exc:
        raise AnswerUnavailable(str(exc)) from exc

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

    if not hits:
        # No evidence -> fixed answer, and the generation gateway is NOT called.
        return {"answer": NO_MATCH_MESSAGE, "citations": []}

    messages = (
        [{"role": "system", "content": _SYSTEM_PROMPT}]
        + _sanitize_history(history)
        + [{"role": "user", "content": _build_sources_message(question, hits)}]
    )
    try:
        answer_text = model_gateway.chat(config, messages)
    except model_gateway.GatewayError as exc:
        raise AnswerUnavailable(str(exc)) from exc

    return {"answer": answer_text, "citations": citations}
