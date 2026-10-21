"""Repository for MCP registry: servers, discovery cache, call logs.

All queries are class-scoped by construction. The token column is write-only
from the API's perspective — no repository helper ever returns it in API
shape (`_server_dict` maps it to a hasToken boolean). Callers own the
transaction.
"""
import json

import pymysql

_SERVER_COLS = "id, class_id, name, base_url, token, status, created_at, updated_at"


def _server_dict(row: dict | None) -> dict | None:
    """API shape: token replaced by the hasToken boolean."""
    if row is None:
        return None
    row = dict(row)
    row["has_token"] = bool(row.pop("token", None))
    row["status"] = row.get("status") or "disconnected"
    return row


def list_by_class(conn, class_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SERVER_COLS} FROM mcp_servers WHERE class_id = %s ORDER BY id",
            (class_id,),
        )
        rows = cur.fetchall()
    return [r for r in (_server_dict(row) for row in rows) if r]


def find(conn, server_id: int, class_id: int) -> dict | None:
    """Return the server only when it belongs to the given class."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SERVER_COLS} FROM mcp_servers WHERE id = %s AND class_id = %s",
            (server_id, class_id),
        )
        row = cur.fetchone()
    return _server_dict(row)


def find_by_name(conn, name: str, class_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SERVER_COLS} FROM mcp_servers WHERE name = %s AND class_id = %s",
            (name, class_id),
        )
        row = cur.fetchone()
    return _server_dict(row)


def create(conn, class_id: int, name: str, base_url: str, token: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mcp_servers (class_id, name, base_url, token) "
            "VALUES (%s, %s, %s, %s)",
            (class_id, name, base_url, (token or "").strip() or None),
        )
        return int(cur.lastrowid)


def update(
    conn,
    server_id: int,
    name: str | None = None,
    base_url: str | None = None,
    token: str | None = None,
) -> None:
    """Partial update; passing token='' clears it. Caller commits."""
    sets, args = [], []
    if name is not None:
        sets.append("name = %s")
        args.append(name)
    if base_url is not None:
        sets.append("base_url = %s")
        args.append(base_url)
    if token is not None:
        sets.append("token = %s")
        args.append(token.strip() or None)
    if not sets:
        return
    args.append(server_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE mcp_servers SET {', '.join(sets)} WHERE id = %s", args)


def raw_token(conn, server_id: int) -> str | None:
    """Read the raw token for outbound calls (host-side only, never logged)."""
    with conn.cursor() as cur:
        cur.execute("SELECT token FROM mcp_servers WHERE id = %s", (server_id,))
        row = cur.fetchone()
    return (row or {}).get("token")


def set_status(conn, server_id: int, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE mcp_servers SET status = %s WHERE id = %s", (status, server_id))


def delete(conn, server_id: int) -> None:
    """Delete the server; tools cache cascades, call logs keep via SET NULL."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mcp_servers WHERE id = %s", (server_id,))


# ---------------------------------------------------------------------------
# Discovery cache
# ---------------------------------------------------------------------------

def replace_tools(conn, server_id: int, tools: list[dict]) -> None:
    """Wholesale replacement: the cache always equals the last successful
    discovery result (never grows by appending)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mcp_tools_cache WHERE server_id = %s", (server_id,))
        for t in tools:
            cur.execute(
                "INSERT INTO mcp_tools_cache (server_id, name, description, input_schema) "
                "VALUES (%s, %s, %s, %s)",
                (
                    server_id,
                    t.get("name", ""),
                    t.get("description") or "",
                    json.dumps(t.get("inputSchema") or {}, ensure_ascii=False),
                ),
            )


def clear_tools(conn, server_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mcp_tools_cache WHERE server_id = %s", (server_id,))


def tools_for_server(conn, server_id: int) -> list[dict]:
    """Discovered tools with input_schema parsed into a dict."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, server_id, name, description, input_schema "
            "FROM mcp_tools_cache WHERE server_id = %s ORDER BY id",
            (server_id,),
        )
        rows = cur.fetchall()
    out = []
    for row in rows:
        row = dict(row)
        raw = row.get("input_schema")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = {}
        row["input_schema"] = raw or {}
        out.append(row)
    return out


def tool_exists(conn, server_id: int, tool_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM mcp_tools_cache WHERE server_id = %s AND name = %s",
            (server_id, tool_name),
        )
        return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Call audit logs
# ---------------------------------------------------------------------------

def append_call(
    conn,
    class_id: int,
    server_id: int | None,
    server_name: str,
    tool_name: str,
    status: str,
    detail: str | None,
    user_id: int,
    conversation_id: int,
    round_no: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mcp_call_logs (class_id, server_id, server_name, tool_name, "
            "status, detail, user_id, conversation_id, round_no) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                class_id,
                server_id,
                server_name,
                tool_name,
                status,
                (detail or "")[:500] or None,
                user_id,
                conversation_id,
                round_no,
            ),
        )


def list_calls(conn, class_id: int, limit: int = 50) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, class_id, server_id, server_name, tool_name, status, detail, "
            "user_id, conversation_id, round_no, created_at "
            "FROM mcp_call_logs WHERE class_id = %s ORDER BY id DESC LIMIT %s",
            (class_id, int(limit)),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]
