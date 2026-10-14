"""Repository for skills (class-scoped guided skills).

Rows carry both the parsed fields and the raw source text. `tools` is stored
as a JSON string and exposed as a list. All queries are class-scoped.
Callers own the transaction.
"""
import json

import pymysql

_COLS = "id, class_id, name, `trigger`, tools, subject, description, source, enabled"


def _serialize(row: dict | None) -> dict | None:
    """Convert a row to the API shape (tools JSON string -> list)."""
    if row is None:
        return None
    row = dict(row)
    raw_tools = row.get("tools")
    if isinstance(raw_tools, str):
        try:
            row["tools"] = json.loads(raw_tools)
        except ValueError:
            row["tools"] = []
    elif raw_tools is None:
        row["tools"] = []
    row["enabled"] = bool(row["enabled"])
    return row


def list_by_class(
    conn: pymysql.connections.Connection, class_id: int, enabled_only: bool = False
) -> list[dict]:
    sql = f"SELECT {_COLS} FROM skills WHERE class_id = %s"
    if enabled_only:
        sql += " AND enabled = 1"
    sql += " ORDER BY id"
    with conn.cursor() as cur:
        cur.execute(sql, (class_id,))
        rows = cur.fetchall()
    return [r for r in (_serialize(row) for row in rows) if r]


def find(
    conn: pymysql.connections.Connection, skill_id: int, class_id: int
) -> dict | None:
    """Return the skill only when it belongs to the given class."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM skills WHERE id = %s AND class_id = %s",
            (skill_id, class_id),
        )
        row = cur.fetchone()
    return _serialize(row)


def create(conn: pymysql.connections.Connection, class_id: int, fields: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO skills (class_id, name, `trigger`, tools, subject, "
            "description, source, enabled) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                class_id,
                fields["name"],
                fields.get("trigger", ""),
                json.dumps(fields.get("tools") or [], ensure_ascii=False),
                fields.get("subject", ""),
                fields["description"],
                fields["source"],
                1 if fields.get("enabled", True) else 0,
            ),
        )
        return int(cur.lastrowid)


def update(conn: pymysql.connections.Connection, skill_id: int, fields: dict) -> None:
    """Replace the parsed fields + source (caller commits)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE skills SET name = %s, `trigger` = %s, tools = %s, subject = %s, "
            "description = %s, source = %s, enabled = %s WHERE id = %s",
            (
                fields["name"],
                fields.get("trigger", ""),
                json.dumps(fields.get("tools") or [], ensure_ascii=False),
                fields.get("subject", ""),
                fields["description"],
                fields["source"],
                1 if fields.get("enabled", True) else 0,
                skill_id,
            ),
        )


def delete(conn: pymysql.connections.Connection, skill_id: int) -> None:
    """Delete the skill; agent_skills rows cascade (caller commits)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM skills WHERE id = %s", (skill_id,))
