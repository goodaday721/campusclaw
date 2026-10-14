"""Repository for class_prompts (one system prompt per class)."""
import pymysql


def get(conn: pymysql.connections.Connection, class_id: int) -> str | None:
    """Return the class prompt body, or None when the class has none."""
    with conn.cursor() as cur:
        cur.execute("SELECT body FROM class_prompts WHERE class_id = %s", (class_id,))
        row = cur.fetchone()
    return row["body"] if row else None


def upsert(conn: pymysql.connections.Connection, class_id: int, body: str) -> None:
    """Insert or update the class prompt (caller commits)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO class_prompts (class_id, body) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE body = VALUES(body)",
            (class_id, body),
        )
