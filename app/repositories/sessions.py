"""Repository for server-side session records (JWT jti registry).

The JWT is only the credential envelope; this table is the source of truth
for revocation. ``id`` stores the token's ``jti`` (32-char uuid4 hex, fits
the VARCHAR(128) primary key), ``expires_at`` mirrors the token's ``exp``.
"""
import pymysql
from datetime import datetime, timezone


def create(
    conn: pymysql.connections.Connection,
    jti: str,
    user_id: int,
    expires_at,
) -> str:
    """Insert a session row for an issued token and return its jti."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
            (jti, user_id, expires_at),
        )
    conn.commit()
    return jti


def find_valid(conn: pymysql.connections.Connection, jti: str | None) -> dict | None:
    """Return the session joined with its user row if the jti exists and is unexpired."""
    if not jti:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id AS session_id, s.user_id, u.username, u.role, u.class_id "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.id = %s AND s.expires_at > %s",
            (jti, _now()),
        )
        return cur.fetchone()


def delete(conn: pymysql.connections.Connection, jti: str | None) -> None:
    """Delete a session row (logout)."""
    if not jti:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE id = %s", (jti,))
    conn.commit()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
