"""Repository for knowledge_entries (material fulltext ingestion)."""
import pymysql


def create(
    conn: pymysql.connections.Connection,
    material_id: int,
    class_id: int,
    content: str,
    source: str,
) -> int:
    """Insert one knowledge entry in the caller's transaction; return its id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO knowledge_entries (material_id, class_id, content, source) "
            "VALUES (%s, %s, %s, %s)",
            (material_id, class_id, content, source),
        )
        return int(cur.lastrowid)


def find_by_material_id(
    conn: pymysql.connections.Connection, material_id: int
) -> dict | None:
    """Return the knowledge entry for a material, if any."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, material_id, class_id, content, source "
            "FROM knowledge_entries WHERE material_id = %s",
            (material_id,),
        )
        return cur.fetchone()
