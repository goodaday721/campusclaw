"""Audit recording helper (SEC-07).

`record` is best-effort: it opens its own connection so callers never have to
change their transaction shape, and it swallows/logs write failures so an
audit outage can never turn a successful business operation into a 500.
`insert_commit` writes inside the caller's connection when the operation and
its audit row should be one transaction (worker grading).
"""
import json
import sys

from app.db.connection import get_connection
from app.repositories import audit as repo


def record(
    db: dict,
    *,
    class_id: int,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    skill_name: str | None = None,
    detail: dict | None = None,
) -> None:
    """Write one audit row in its own transaction; never raises."""
    try:
        conn = get_connection(db)
        try:
            repo.insert(
                conn,
                class_id=class_id,
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                skill_name=skill_name,
                detail=detail,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # audit must not break the business path
        sys.stdout.write(
            json.dumps(
                {"event": "audit_write_failed", "error": type(exc).__name__,
                 "action": action, "targetType": target_type},
                ensure_ascii=False,
            )
            + "\n"
        )
        sys.stdout.flush()


def insert_commit(
    conn,
    *,
    class_id: int,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    skill_name: str | None = None,
    detail: dict | None = None,
) -> None:
    """Insert inside the caller's transaction; the caller commits."""
    repo.insert(
        conn,
        class_id=class_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        skill_name=skill_name,
        detail=detail,
    )
