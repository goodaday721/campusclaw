"""Repository for knowledge_chunks (lesson-4 retrieval corpus).

All read/search queries MUST include the session class_id. Chunk text is stored
only here; the vector store gets vectors keyed by chunk id, never the text.
Callers own the transaction (inserts/deletes do not commit).
"""
import pymysql


def insert_many(conn: pymysql.connections.Connection, rows: list[dict]) -> list[int]:
    """Insert chunk rows inside the caller's transaction; return new ids."""
    ids: list[int] = []
    if not rows:
        return ids
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                "INSERT INTO knowledge_chunks "
                "(material_id, knowledge_entry_id, class_id, chunk_index, "
                "chunk_text, char_start, char_end, strategy, "
                "index_status, embedding_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    row["material_id"],
                    row["knowledge_entry_id"],
                    row["class_id"],
                    row["chunk_index"],
                    row["chunk_text"],
                    row["char_start"],
                    row["char_end"],
                    row["strategy"],
                    row.get("index_status", "ready"),
                    row.get("embedding_status", "pending"),
                ),
            )
            ids.append(int(cur.lastrowid))
    return ids


def delete_by_material(conn: pymysql.connections.Connection, material_id: int) -> int:
    """Delete all chunks of a material inside the caller's transaction."""
    with conn.cursor() as cur:
        deleted = cur.execute(
            "DELETE FROM knowledge_chunks WHERE material_id = %s",
            (material_id,),
        )
    return int(deleted)


def mark_embedding_status(
    conn: pymysql.connections.Connection, chunk_ids: list[int], status: str
) -> None:
    """Update embedding_status of the given chunks (caller commits)."""
    if not chunk_ids:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE knowledge_chunks SET embedding_status = %s WHERE id = %s",
            [(status, cid) for cid in chunk_ids],
        )


def find_by_material(
    conn: pymysql.connections.Connection, material_id: int
) -> list[dict]:
    """Return a material's chunks ordered by chunk_index."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, material_id, knowledge_entry_id, class_id, chunk_index, "
            "chunk_text, char_start, char_end, strategy, index_status, created_at "
            "FROM knowledge_chunks WHERE material_id = %s ORDER BY chunk_index",
            (material_id,),
        )
        return list(cur.fetchall())


def get_ready_by_ids_scoped(
    conn: pymysql.connections.Connection, chunk_ids: list[int], class_id: int
) -> dict[int, dict]:
    """Fetch ready chunks by id, re-checking the session class id.

    Returns a dict keyed by chunk id. Any id belonging to another class (or not
    ready) is silently absent — the second class-scope gate after Qdrant.
    """
    if not chunk_ids:
        return {}
    placeholders = ",".join(["%s"] * len(chunk_ids))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, material_id, knowledge_entry_id, class_id, chunk_index, "
            "chunk_text, char_start, char_end, strategy, index_status "
            f"FROM knowledge_chunks WHERE index_status = 'ready' "
            f"AND class_id = %s AND id IN ({placeholders})",
            (class_id, *chunk_ids),
        )
        rows = cur.fetchall()
    return {int(r["id"]): r for r in rows}


def keyword_search(
    conn: pymysql.connections.Connection, class_id: int, query: str, limit: int
) -> list[int]:
    """ngram FULLTEXT natural-language search; ready chunks of this class only.

    Returns chunk ids ordered by MySQL fulltext relevance. Never touches the
    embedding gateway or Qdrant.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM knowledge_chunks "
            "WHERE MATCH (chunk_text) AGAINST (%s IN NATURAL LANGUAGE MODE) "
            "AND class_id = %s AND index_status = 'ready' "
            "LIMIT %s",
            (query, class_id, int(limit)),
        )
        return [int(r["id"]) for r in cur.fetchall()]


def find_materials_without_chunks(conn: pymysql.connections.Connection) -> list[dict]:
    """Return (material_id, knowledge_entry_id, class_id) lacking any chunk.

    Used by startup backfill: existing materials are never re-chunked.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.material_id AS material_id, e.id AS knowledge_entry_id, "
            "e.class_id AS class_id "
            "FROM knowledge_entries e "
            "LEFT JOIN knowledge_chunks c ON c.material_id = e.material_id "
            "WHERE c.id IS NULL"
        )
        return list(cur.fetchall())
