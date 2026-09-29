"""MySQL database connection helpers (PyMySQL).

All connections use DictCursor (row["col"] access, matching the previous
sqlite3.Row behaviour), utf8mb4, and autocommit=False — transactions are
controlled explicitly by callers (commit/rollback).
"""
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor


def get_connection(db: dict) -> pymysql.connections.Connection:
    """Open a MySQL connection.

    `db` carries host/port/user/password/database (see Config.db_config).
    """
    return pymysql.connect(
        host=db["host"],
        port=int(db["port"]),
        user=db["user"],
        password=db["password"],
        database=db["database"],
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script into individual executable statements.

    pymysql executes one statement per call, so migrate scripts are split on
    semicolons; segments that are empty or comments-only are dropped.
    """
    statements = []
    for chunk in sql.split(";"):
        # Drop comment-only lines, then check anything executable remains
        lines = [
            line for line in chunk.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if lines:
            statements.append(chunk.strip())
    return statements


def run_migration(conn: pymysql.connections.Connection, sql_path: str) -> None:
    """Execute a migration SQL script statement by statement, then commit."""
    sql = Path(sql_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        for statement in _split_statements(sql):
            cur.execute(statement)
    conn.commit()
