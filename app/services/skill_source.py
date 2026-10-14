"""Parse the single-source skill text into structured fields.

A skill is authored as one paste-able text block (teacher prototype style):

    名称：方程解题引导
    适用条件：一元一次方程、二元一次方程组
    工具：knowledge_search
    资料：数学
    启用：是

    <blank line>
    引导指令正文（description，注入系统提示词的部分）

Line fields are recognised only BEFORE the first blank line; everything after
it is the verbatim description. Full-width and half-width colons both work.
`名称` and a non-empty description are required.
"""
import re

LINE_RE = re.compile(r"^(名称|适用条件|工具|资料|启用)[：:]\s*(.*)$")


class SkillSourceError(ValueError):
    """Raised when the source text cannot be parsed into a valid skill."""


def parse(source: str) -> dict:
    """Return {name, trigger, tools, subject, description, enabled, source}.

    Raises SkillSourceError when `名称` or the description is missing/empty.
    """
    if not isinstance(source, str) or not source.strip():
        raise SkillSourceError("source must not be empty")

    fields: dict = {
        "name": "",
        "trigger": "",
        "tools": [],
        "subject": "",
        "description": "",
        "enabled": True,
        "source": source,
    }

    head_lines: list[str] = []
    body_lines: list[str] = []
    at_head = True
    for raw in source.strip("\n").splitlines():
        if at_head:
            if not raw.strip():
                at_head = False
                continue
            head_lines.append(raw)
        else:
            body_lines.append(raw)

    description = "\n".join(body_lines).strip()
    if not description:
        raise SkillSourceError("source must contain guidance text after a blank line")
    fields["description"] = description

    seen_name = False
    for line in head_lines:
        match = LINE_RE.match(line.strip())
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key == "名称":
            fields["name"] = value
            seen_name = True
        elif key == "适用条件":
            fields["trigger"] = value
        elif key == "工具":
            fields["tools"] = [
                t.strip() for t in re.split(r"[,，;；]", value) if t.strip()
            ]
        elif key == "资料":
            fields["subject"] = value
        elif key == "启用":
            if value in ("是", "true", "True", "1"):
                fields["enabled"] = True
            elif value in ("否", "false", "False", "0"):
                fields["enabled"] = False
            else:
                raise SkillSourceError("启用 must be 是 or 否")

    if not seen_name or not fields["name"]:
        raise SkillSourceError("source must contain a 名称： line")
    return fields
