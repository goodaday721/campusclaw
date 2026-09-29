"""Repository for server-side sessions (opaque random tokens)."""
import secrets
from datetime import datetime, timedelta, timezone

import pymysql


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create(conn: pymysql.connections.Connection, user_id: int, ttl_hours: int) -> str:
    """Insert a new session row and return its random token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )
    conn.commit()
    return token


def find_valid(conn: pymysql.connections.Connection, token: str | None) -> dict | None:
    """Return the session joined with its user row if the token exists and is unexpired."""
    if not token:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id AS session_id, s.user_id, u.username, u.role, u.class_id "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.id = %s AND s.expires_at > %s",
            (token, _now()),
        )
        return cur.fetchone()


def delete(conn: pymysql.connections.Connection, token: str | None) -> None:
    """Delete a session row (logout / re-issue on login)."""
    if not token:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE id = %s", (token,))
    conn.commit()
