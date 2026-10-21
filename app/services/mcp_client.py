"""MCP client: JSON-RPC 2.0 over the Streamable HTTP transport (lesson 6).

Host-side counterpart of the self-built mcp-server. Every request carries the
server's own Bearer token (stored server-side only); the token is never
logged and never echoed in error messages. Three error classes let callers
distinguish "tool execution reported a problem" (McpToolError — the server
was reachable and answered) from transport/auth failures.
"""
import json

import requests

PROTOCOL_VERSION = "2024-11-05"


class McpError(Exception):
    """Base class for MCP client failures."""


class McpUnavailable(McpError):
    """Server unreachable, timed out, or returned 5xx."""


class McpRejected(McpError):
    """Server rejected the request (401/403/other 4xx) — usually a bad token."""


class McpToolError(McpError):
    """Server reachable but the JSON-RPC call failed or the tool self-reported
    an error (isError=true). The message carries the readable reason."""


def _timeout(config) -> tuple[float, float]:
    return (config.mcp_timeout_connect, config.mcp_timeout_read)


def _rpc(base_url: str, token: str, method: str, params: dict, config) -> dict:
    """One JSON-RPC round trip; returns the result object or raises McpError."""
    url = base_url.rstrip("/") + "/mcp"
    headers = {
        "Authorization": f"Bearer {token or ''}",
        "Content-Type": "application/json",
    }
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout(config))
    except requests.RequestException as exc:
        raise McpUnavailable(f"无法连接 MCP 服务器（{type(exc).__name__}），请检查地址与网络") from exc

    if resp.status_code in (401, 403):
        raise McpRejected("令牌缺失或错误（服务器返回 401/403），请核对 Bearer 令牌")
    if 500 <= resp.status_code < 600:
        raise McpUnavailable(f"MCP 服务器内部错误（HTTP {resp.status_code}）")
    if not (200 <= resp.status_code < 300):
        raise McpRejected(f"MCP 服务器拒绝了请求（HTTP {resp.status_code}）")

    try:
        data = resp.json()
    except ValueError as exc:
        raise McpUnavailable("MCP 服务器返回了无法解析的响应") from exc
    if not isinstance(data, dict):
        raise McpUnavailable("MCP 服务器返回了非 JSON-RPC 响应")
    if "error" in data:
        err = data.get("error") or {}
        raise McpToolError(
            f"JSON-RPC 错误 {err.get('code')}: {err.get('message', '未知错误')}"
        )
    if "result" not in data:
        raise McpUnavailable("MCP 服务器响应缺少 result")
    return data["result"]


def initialize(base_url: str, token: str, config) -> dict:
    """Handshake: negotiate protocol version + capabilities."""
    return _rpc(base_url, token, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "clientInfo": {"name": "campusclaw-host", "version": "1.0.0"},
    }, config)


def list_tools(base_url: str, token: str, config) -> list[dict]:
    """Discovery: return the server's tool list (name/description/inputSchema)."""
    result = _rpc(base_url, token, "tools/list", {}, config)
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise McpUnavailable("tools/list 响应缺少 tools 清单")
    return [t for t in tools if isinstance(t, dict) and t.get("name")]


def call_tool(base_url: str, token: str, tool_name: str, arguments: dict, config) -> str:
    """Execute one tool; return the concatenated text content.

    Raises McpToolError when the tool self-reports an error (isError=true).
    """
    result = _rpc(base_url, token, "tools/call",
                  {"name": tool_name, "arguments": arguments}, config)
    content = result.get("content")
    if not isinstance(content, list):
        raise McpToolError("tools/call 响应缺少 content")
    text = "".join(
        item.get("text", "") for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    )
    if result.get("isError"):
        raise McpToolError(text or "工具执行失败（isError=true）")
    return text
