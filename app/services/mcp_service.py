"""Host-side MCP orchestration helpers (lesson 6).

Reference validation ("tool@server" format + the four config-time checks),
candidate-set construction (least privilege: only the tools this turn's
skills actually reference, and only from CONNECTED servers), and the prompt
injection scan applied to tool results before they enter the message stream.
"""
import re

from app.repositories import mcp as mcp_repo

# Tool names come from the tool server: lowercase start, no hyphens allowed.
# Server names are human-chosen: hyphens allowed after the first character.
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SERVER_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
REFERENCE_RE = re.compile(r"^([a-z][a-z0-9_]*)@([a-z][a-z0-9_-]*)$")

BUILTIN_TOOLS = {"knowledge_search"}

# Known instruction-style patterns in tool output. A hit drops the WHOLE
# result (not just the matching line) and substitutes a fixed note — a
# tampered text may be self-contradictory, so partial removal is unsound.
INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"忽略(之前|上面|以上|先前|前面)?(的)?(所有)?(指令|提示|说明|规则|要求)",
        r"无视(之前|上面|以上)?(的)?(所有)?(指令|提示|说明|规则|要求)",
        r"不要遵守.{0,10}(指令|规则|提示)",
        r"你现在是", r"从现在起你是", r"你(必须|应该)扮演",
        r"disregard\s+(all\s+)?(previous|prior|above)", r"ignore\s+(all\s+)?"
        r"(previous|prior|above)", r"system\s*prompt",
    )
]

INJECTION_NOTE = "（该工具返回内容未通过安全检查，已忽略。）"


class ReferenceError_(ValueError):
    """Invalid or unusable MCP tool reference (config-time rejection)."""


def parse_reference(value: str) -> tuple[str, str] | None:
    """Return (tool_name, server_name) for a valid reference, else None."""
    if not isinstance(value, str):
        return None
    m = REFERENCE_RE.match(value.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def validate_reference(conn, class_id: int, value: str) -> None:
    """Config-time four checks: format -> registered -> connected -> listed.

    Raises ReferenceError_ with a readable, user-facing message. Unregistered
    and cross-class server names read the same ("未登记"), so the error can't
    be used to probe other classes' registries.
    """
    if not isinstance(value, str) or not value.strip():
        raise ReferenceError_("工具引用不能为空")
    ref = value.strip()
    if ref in BUILTIN_TOOLS:
        return
    parsed = parse_reference(ref)
    if parsed is None:
        if "@" not in ref:
            raise ReferenceError_(
                f"工具引用“{ref}”不合法：MCP 工具须写成“工具名@服务器名”，"
                "内置工具 knowledge_search 可单独使用"
            )
        tool, server = ref.split("@", 1)
        if not TOOL_NAME_RE.match(tool):
            raise ReferenceError_(
                f"工具引用“{ref}”不合法：工具名须以小写字母开头，只含小写字母、"
                "数字与下划线（不含连字符）"
            )
        raise ReferenceError_(
            f"工具引用“{ref}”不合法：服务器名须以小写字母开头，只含小写字母、"
            "数字、下划线与连字符"
        )
    tool, server = parsed
    row = mcp_repo.find_by_name(conn, server, class_id)
    if row is None:
        raise ReferenceError_(
            f"工具引用“{ref}”不可用：服务器“{server}”未登记或不可用"
        )
    if row["status"] != "connected":
        raise ReferenceError_(
            f"工具引用“{ref}”不可用：服务器“{server}”当前未连接，请先在管理页连接"
        )
    if not mcp_repo.tool_exists(conn, row["id"], tool):
        raise ReferenceError_(
            f"工具引用“{ref}”不可用：工具“{tool}”不在服务器“{server}”"
            "最近一次发现的清单中，请先连接刷新清单"
        )


def sanitize_tool_text(text: str) -> str:
    """Prompt-injection scan over tool output: a pattern hit drops the whole
    text and substitutes a fixed note."""
    if not isinstance(text, str) or not text.strip():
        return text or ""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return INJECTION_NOTE
    return text


def build_candidates(conn, class_id: int, refs: list[str]) -> dict:
    """Resolve MCP references into the turn's candidate set.

    Returns {"declarations": [...OpenAI tool declarations...],
             "by_tool": {tool_name: candidate},
             "unresolved": [{"ref", "server_id"|None, "server_name"}]} where each candidate carries
    server addressing (id, name, base_url, token) and the reference string.
    Only CONNECTED servers with the tool present in the cached discovery
    result make it in — that is the runtime re-check, kept deliberately light
    (config-time did the heavy validation when the skill was saved). References
    that fail the runtime re-check land in "unresolved" so the caller can
    record them as denied instead of silently dropping them.
    """
    declarations, by_tool, unresolved = [], {}, []
    seen: set[str] = set()
    for ref in dict.fromkeys(r.strip() for r in refs if r):
        parsed = parse_reference(ref)
        if parsed is None:
            continue
        tool, server = parsed
        if tool in seen:
            continue
        row = mcp_repo.find_by_name(conn, server, class_id)
        if row is None or row["status"] != "connected":
            unresolved.append({"ref": ref, "server_id": row["id"] if row else None,
                               "server_name": server})
            continue
        tools = {t["name"]: t for t in mcp_repo.tools_for_server(conn, row["id"])}
        found = tools.get(tool)
        if found is None:
            unresolved.append({"ref": ref, "server_id": row["id"],
                               "server_name": server})
            continue
        seen.add(tool)
        by_tool[tool] = {
            "ref": ref,
            "tool_name": tool,
            "server_id": row["id"],
            "server_name": server,
            "base_url": row["base_url"],
            "token": mcp_repo.raw_token(conn, row["id"]),
            "description": found.get("description") or "",
            "input_schema": found.get("input_schema") or {},
        }
        declarations.append({
            "type": "function",
            "function": {
                "name": tool,
                "description": found.get("description") or "",
                "parameters": found.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    return {"declarations": declarations, "by_tool": by_tool, "unresolved": unresolved}
