"""Grade one submission with the course chat gateway (server-side only).

The worker is the only caller: it builds a grading prompt from the assignment
question + reference answer + student answer, asks the gateway for a
`{"score", "feedback"}` JSON object, and degrades gracefully when the model
answers in free text. Gateway errors are raised as-is so the worker can apply
its retry policy.
"""
import json
import re

from app.services import model_gateway

_SYSTEM_PROMPT = (
    "你是课程作业批改老师。请依据参考答案评估学生答案，"
    "只返回一个 JSON 对象，格式为 "
    '{"score": 0-100 的整数, "feedback": "面向学生的简短中文评语"}。'
    "不要输出 JSON 之外的任何内容。"
)


class GradingFailed(Exception):
    """Raised for a non-retryable grading problem (missing context, empty answer)."""


def build_messages(question: str, reference_answer: str, answer: str) -> list[dict]:
    user = (
        f"题目：\n{question}\n\n"
        f"参考答案：\n{reference_answer}\n\n"
        f"学生答案：\n{answer}\n\n"
        "请给出分数与评语。"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_result(text: str) -> tuple[int | None, str]:
    """Parse `{"score", "feedback"}`; free text keeps the raw reply as feedback."""
    raw = (text or "").strip()
    if not raw:
        return None, "模型未返回可读的批改结果"
    data = None
    try:
        data = json.loads(raw)
    except ValueError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group(0))
            except ValueError:
                data = None
    if not isinstance(data, dict):
        return None, raw
    score = data.get("score")
    try:
        score = int(round(float(score)))
    except (TypeError, ValueError):
        score = None
    if score is not None:
        score = max(0, min(100, score))
    feedback = data.get("feedback")
    feedback = str(feedback).strip() if feedback is not None else ""
    return score, feedback or raw


def grade(
    config, question: str, reference_answer: str, answer: str
) -> tuple[int | None, str]:
    """Return (score, feedback). Raises model_gateway errors for the worker."""
    if not (question or "").strip() or not (answer or "").strip():
        raise GradingFailed("题目或学生答案为空")
    text = model_gateway.chat(
        config, build_messages(question, reference_answer or "", answer)
    )
    return parse_result(text)
