"""Materials repository with class-scoped filtering.

All queries MUST include the current user's classId as a WHERE condition.
The bare find_by_id(id) is intentionally NOT provided — use
find_by_id_scoped_to_class(id, classId) instead.
"""
import pymysql
from datetime import datetime, timezone


class MaterialsRepository:
    def __init__(self, conn: pymysql.connections.Connection) -> None:
        self.conn = conn

    def find_by_class(self, class_id: int) -> list[dict]:
        """Return all materials belonging to the given class."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, class_id, uploader_user_id, filename, storage_key, "
                "mime, size, created_at FROM materials WHERE class_id = %s "
                "ORDER BY created_at DESC, id DESC",
                (class_id,),
            )
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    def find_by_id_scoped_to_class(self, material_id: int, class_id: int) -> dict | None:
        """Return a single material, but only if it belongs to the given class."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, class_id, uploader_user_id, filename, storage_key, "
                "mime, size, created_at FROM materials "
                "WHERE id = %s AND class_id = %s",
                (material_id, class_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def create(
        self,
        *,
        class_id: int,
        uploader_user_id: int,
        filename: str,
        storage_key: str,
        mime: str,
        size: int,
    ) -> dict:
        """Insert a new material row WITHOUT committing.

        Commit/rollback is controlled by the caller (upload service runs
        materials + knowledge_entries inserts in one transaction).
        class_id comes from the server session, never the client.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO materials "
                "(class_id, uploader_user_id, filename, storage_key, mime, size, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (class_id, uploader_user_id, filename, storage_key, mime, size, now),
            )
            new_id = cur.lastrowid
        return {
            "id": new_id,
            "class_id": class_id,
            "uploader_user_id": uploader_user_id,
            "filename": filename,
            "storage_key": storage_key,
            "mime": mime,
            "size": size,
            "created_at": now,
        }


def _row_to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "class_id": row["class_id"],
        "uploader_user_id": row["uploader_user_id"],
        "filename": row["filename"],
        "storage_key": row["storage_key"],
        "mime": row["mime"],
        "size": row["size"],
        "created_at": row["created_at"],
    }
