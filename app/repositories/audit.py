"""Repository for audit_logs (SEC-07: queryable audit records).

Every read is class-scoped. `insert` executes inside the caller's transaction
(or a throwaway one via app.services.audit.record); `detail` is stored as JSON.
"""
import json

_COLS = (
    "id, class_id, actor_id, action, target_type, target_id, skill_name, "
    "detail, created_at"
)


def insert(
    conn,
    *,
    class_id: int,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    skill_name: str | None = None,
    detail: dict | None = None,
) -> int:
    payload = json.dumps(detail, ensure_ascii=False) if detail is not None else None
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_logs "
            "(class_id, actor_id, action, target_type, target_id, skill_name, detail) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (class_id, actor_id, action, target_type, target_id, skill_name, payload),
        )
        return int(cur.lastrowid)


def list_by_class(
    conn,
    class_id: int,
    *,
    limit: int = 50,
    action: str | None = None,
    target_type: str | None = None,
) -> list[dict]:
    sql = f"SELECT {_COLS} FROM audit_logs WHERE class_id = %s"
    params: list = [class_id]
    if action:
        sql += " AND action = %s"
        params.append(action)
    if target_type:
        sql += " AND target_type = %s"
        params.append(target_type)
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchall()
