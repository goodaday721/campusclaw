"""Repository for agents (class-scoped assistant personas).

Agents bind skills and materials via join tables; material_ids empty means
"search the whole class library". All queries are class-scoped; callers own
the transaction.
"""
import json

import pymysql


def _with_bindings(conn, row: dict) -> dict:
    """Attach skill_ids / material_ids lists to an agent row."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT skill_id FROM agent_skills WHERE agent_id = %s ORDER BY skill_id",
            (row["id"],),
        )
        row["skillIds"] = [int(r["skill_id"]) for r in cur.fetchall()]
        cur.execute(
            "SELECT material_id FROM agent_materials WHERE agent_id = %s "
            "ORDER BY material_id",
            (row["id"],),
        )
        row["materialIds"] = [int(r["material_id"]) for r in cur.fetchall()]
    row["enabled"] = bool(row["enabled"])
    return row


def list_by_class(
    conn: pymysql.connections.Connection, class_id: int, enabled_only: bool = False
) -> list[dict]:
    sql = (
        "SELECT id, class_id, name, prompt, enabled FROM agents "
        "WHERE class_id = %s"
    )
    if enabled_only:
        sql += " AND enabled = 1"
    sql += " ORDER BY id"
    with conn.cursor() as cur:
        cur.execute(sql, (class_id,))
        rows = cur.fetchall()
    return [_with_bindings(conn, dict(row)) for row in rows]


def find(
    conn: pymysql.connections.Connection, agent_id: int, class_id: int
) -> dict | None:
    """Return the agent only when it belongs to the given class."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, class_id, name, prompt, enabled FROM agents "
            "WHERE id = %s AND class_id = %s",
            (agent_id, class_id),
        )
        row = cur.fetchone()
    return _with_bindings(conn, dict(row)) if row else None


def skills_for_agent(
    conn: pymysql.connections.Connection, agent_id: int
) -> list[dict]:
    """Enabled skills bound to the agent, in binding order (chat injection)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.name, s.description, s.enabled, s.tools FROM agent_skills ask "
            "JOIN skills s ON s.id = ask.skill_id "
            "WHERE ask.agent_id = %s AND s.enabled = 1 ORDER BY ask.skill_id",
            (agent_id,),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        row = dict(r)
        raw = row.get("tools")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = []
        row["tools"] = raw or []
        out.append(row)
    return out


def material_ids_for_agent(
    conn: pymysql.connections.Connection, agent_id: int
) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT material_id FROM agent_materials WHERE agent_id = %s",
            (agent_id,),
        )
        rows = cur.fetchall()
    return [int(r["material_id"]) for r in rows]


def _set_bindings(
    conn,
    agent_id: int,
    class_id: int,
    skill_ids: list[int],
    material_ids: list[int],
) -> None:
    """Replace bindings after the caller has validated class ownership."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_skills WHERE agent_id = %s", (agent_id,))
        for sid in skill_ids:
            cur.execute(
                "INSERT INTO agent_skills (agent_id, skill_id) VALUES (%s, %s)",
                (agent_id, sid),
            )
        cur.execute(
            "DELETE FROM agent_materials WHERE agent_id = %s", (agent_id,)
        )
        for mid in material_ids:
            cur.execute(
                "INSERT INTO agent_materials (agent_id, material_id) VALUES (%s, %s)",
                (agent_id, mid),
            )


def create(
    conn: pymysql.connections.Connection,
    class_id: int,
    name: str,
    prompt: str | None,
    enabled: bool,
    skill_ids: list[int],
    material_ids: list[int],
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agents (class_id, name, prompt, enabled) "
            "VALUES (%s, %s, %s, %s)",
            (class_id, name, prompt, 1 if enabled else 0),
        )
        agent_id = int(cur.lastrowid)
    _set_bindings(conn, agent_id, class_id, skill_ids, material_ids)
    return agent_id


def update(
    conn: pymysql.connections.Connection,
    agent_id: int,
    name: str,
    prompt: str | None,
    enabled: bool,
    skill_ids: list[int],
    material_ids: list[int],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE agents SET name = %s, prompt = %s, enabled = %s WHERE id = %s",
            (name, prompt, 1 if enabled else 0, agent_id),
        )
    _set_bindings(conn, agent_id, None, skill_ids, material_ids)
