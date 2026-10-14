"""Shared helpers for apitest cases.

Lowercase filename on purpose: the runner only picks up files starting with
an uppercase letter as cases, so helpers are never executed standalone.
"""
import json
import os

import pymysql


def db_query_all(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT against the main database (inside the compose network)."""
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "app"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "campusclaw"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def db_query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = db_query_all(sql, params)
    return rows[0] if rows else None


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data_dict) frames in order."""
    frames = []
    for block in text.split("\n\n"):
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if event is None:
            continue
        try:
            frames.append((event, json.loads(data) if data else None))
        except ValueError:
            frames.append((event, data))
    return frames
