"""Repository for conversations and messages (SSE chat transcript).

Conversations belong to one user in one class; cross-class access is handled
by find_owned returning None. Callers own the transaction.
"""
import json

import pymysql

TITLE_MAX_CHARS = 30


def list_by_user(
    conn: pymysql.connections.Connection, user_id: int, class_id: int
) -> list[dict]:
    """The user's conversations in their class, newest first, with agent name."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id, c.user_id, c.class_id, c.agent_id, c.title, "
            "c.created_at, c.updated_at, a.name AS agent_name "
            "FROM conversations c JOIN agents a ON a.id = c.agent_id "
            "WHERE c.user_id = %s AND c.class_id = %s "
            "ORDER BY c.updated_at DESC, c.id DESC",
            (user_id, class_id),
        )
        rows = cur.fetchall()
    result = []
    for row in rows:
        row = dict(row)
        row.pop("user_id")
        result.append(row)
    return result


def create(
    conn: pymysql.connections.Connection,
    user_id: int,
    class_id: int,
    agent_id: int,
) -> int:
    """Create an empty conversation; the title is set on the first message."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (user_id, class_id, agent_id, title) "
            "VALUES (%s, %s, %s, '')",
            (user_id, class_id, agent_id),
        )
        return int(cur.lastrowid)


def find_owned(
    conn: pymysql.connections.Connection,
    conversation_id: int,
    user_id: int,
    class_id: int,
) -> dict | None:
    """Return the conversation only for its owner in the same class."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, user_id, class_id, agent_id, title, created_at, updated_at "
            "FROM conversations WHERE id = %s AND user_id = %s AND class_id = %s",
            (conversation_id, user_id, class_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def find_by_id(
    conn: pymysql.connections.Connection, conversation_id: int
) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, user_id, class_id, agent_id, title, created_at, updated_at "
            "FROM conversations WHERE id = %s",
            (conversation_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def append_message(
    conn: pymysql.connections.Connection,
    conversation_id: int,
    role: str,
    content: str,
    citations: list | None = None,
    skill_name: str | None = None,
) -> int:
    """Append a message; the first user message becomes the conversation title."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (conversation_id, role, content, citations, "
            "skill_name) VALUES (%s, %s, %s, %s, %s)",
            (
                conversation_id,
                role,
                content,
                json.dumps(citations, ensure_ascii=False) if citations is not None else None,
                skill_name,
            ),
        )
        message_id = int(cur.lastrowid)
        if role == "user":
            cur.execute(
                "SELECT title FROM conversations WHERE id = %s", (conversation_id,)
            )
            title = (cur.fetchone() or {}).get("title") or ""
            if not title:
                cur.execute(
                    "UPDATE conversations SET title = %s WHERE id = %s",
                    (content.strip()[:TITLE_MAX_CHARS], conversation_id),
                )
    return message_id


def messages_for(
    conn: pymysql.connections.Connection, conversation_id: int
) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, role, content, citations, skill_name, created_at "
            "FROM messages WHERE conversation_id = %s ORDER BY id",
            (conversation_id,),
        )
        rows = cur.fetchall()
    result = []
    for row in rows:
        row = dict(row)
        raw = row.get("citations")
        if isinstance(raw, str):
            try:
                row["citations"] = json.loads(raw)
            except ValueError:
                row["citations"] = []
        result.append(row)
    return result


def recent_messages(
    conn: pymysql.connections.Connection, conversation_id: int, limit: int = 6
) -> list[dict]:
    """The last `limit` turns (oldest -> newest) as plain {role, content}."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT role, content FROM messages WHERE conversation_id = %s "
            "ORDER BY id DESC LIMIT %s",
            (conversation_id, limit),
        )
        rows = cur.fetchall()
    return [
        {"role": row["role"], "content": row["content"]}
        for row in reversed(rows)
    ]
