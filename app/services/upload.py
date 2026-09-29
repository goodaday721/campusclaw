"""Upload service: whitelist validation, disk write, transactional dual-table ingest.

Flow (per lesson-3 spec):
  teacher check (403, before any write) → .txt/.md whitelist + size cap (4xx,
  no file, no rows) → server-generated storage name → write file to disk →
  read fulltext → ONE transaction inserts materials + knowledge_entries with
  the same session class_id. Any DB failure rolls back BOTH tables and removes
  the written file: no orphan files, no orphan records.
"""
import os
import uuid
from pathlib import Path

import pymysql
from werkzeug.datastructures import FileStorage

from app.db.connection import get_connection
from app.repositories import knowledge as knowledge_repo
from app.repositories.materials import MaterialsRepository

ALLOWED_EXTENSIONS = {".txt", ".md"}


class UploadValidationError(Exception):
    """Raised when the upload fails validation; carries the HTTP status code."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class UploadPersistenceError(Exception):
    """Raised when the database transaction fails; file cleanup already done."""


def save_upload(
    db: dict,
    upload_root: Path,
    *,
    file: FileStorage,
    class_id: int,
    uploader_id: int,
    max_size_mb: int,
) -> dict:
    """Validate, persist to disk and ingest into both tables atomically.

    Returns the created material dict. Raises UploadValidationError for
    4xx-level rejections and UploadPersistenceError for transaction failures.
    """
    original_name = file.filename or ""
    ext = Path(original_name).suffix.lower()

    # 1. Whitelist: only .txt / .md — reject before any disk or DB write
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"file type not allowed: {ext or '(none)'}", 415)

    # 2. Size cap
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_bytes = max_size_mb * 1024 * 1024
    if size > max_bytes:
        raise UploadValidationError("file too large", 413)

    # 3. Server-generated storage name — never trust the client filename.
    #    storage_key is relative to the configured upload root.
    storage_name = f"{uuid.uuid4()}{ext}"
    rel_dir = Path("materials") / str(class_id)
    abs_dir = upload_root / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    dest = abs_dir / storage_name
    storage_key = f"{rel_dir.as_posix()}/{storage_name}"

    # 4. Write file to disk
    file.save(str(dest))

    # 5. Read fulltext (these are text files by whitelist)
    raw = dest.read_bytes()
    content = raw.decode("utf-8", errors="replace")

    # 6. One transaction: materials + knowledge_entries, same class_id
    conn = get_connection(db)
    try:
        repo = MaterialsRepository(conn)
        material = repo.create(
            class_id=class_id,
            uploader_user_id=uploader_id,
            filename=original_name,
            storage_key=storage_key,
            mime="text/plain" if ext == ".txt" else "text/markdown",
            size=size,
        )
        knowledge_repo.create(
            conn,
            material_id=int(material["id"]),
            class_id=class_id,
            content=content,
            source=original_name,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        # Clean up the written file — no orphans allowed
        try:
            dest.unlink()
        except OSError:
            pass
        raise UploadPersistenceError("failed to ingest upload") from None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return material
