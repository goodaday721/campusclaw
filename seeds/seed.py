"""Seed script: pre-populate classes, teachers, students, materials + knowledge entries.

Idempotent: uses INSERT IGNORE so repeated runs don't duplicate records.
Passwords are bcrypt-hashed (cost 12) at insert time.
Files are written under UPLOAD_ROOT (defaults to <project>/uploads locally,
/app/uploads in the container).
"""
import os
import sys
from pathlib import Path

import bcrypt
import pymysql

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import resolve_upload_root  # noqa: E402
from app.db.connection import get_connection, run_migration  # noqa: E402

MIGRATIONS = [
    "001_initial_schema.sql",
    "002_sessions_knowledge.sql",
    "003_knowledge_chunks.sql",
]

# Two distinguishable seeded materials (one per class) with fixed ids for idempotency
SEED_MATERIALS = [
    {
        "id": 1,
        "class_id": 1,
        "uploader_user_id": 1,
        "filename": "A班-第3课阅读材料.txt",
        "storage_name": "seed-a-class-material.txt",
        "content": "A班专属阅读材料：服务端会话与班级隔离要点。本文仅A班可见。",
    },
    {
        "id": 2,
        "class_id": 2,
        "uploader_user_id": 2,
        "filename": "B班-第3课阅读材料.txt",
        "storage_name": "seed-b-class-material.txt",
        "content": "B班专属阅读材料：上传入库与两表事务要点。本文仅B班可见。",
    },
]


def hash_password(plain: str) -> str:
    """Return a bcrypt hash (cost 12) for the given password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _seed_materials(conn: pymysql.connections.Connection, upload_root: Path) -> None:
    """Insert two distinguishable per-class materials + knowledge entries + files."""
    for m in SEED_MATERIALS:
        # Write the file only if missing (idempotent)
        rel_key = f"materials/{m['class_id']}/{m['storage_name']}"
        dest = upload_root / rel_key
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(m["content"], encoding="utf-8")

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM materials WHERE id = %s", (m["id"],))
            existing = cur.fetchone()
            if existing is None:
                cur.execute(
                    "INSERT INTO materials (id, class_id, uploader_user_id, filename, "
                    "storage_key, mime, size, created_at) VALUES (%s, %s, %s, %s, %s, "
                    "%s, %s, UTC_TIMESTAMP())",
                    (
                        m["id"],
                        m["class_id"],
                        m["uploader_user_id"],
                        m["filename"],
                        rel_key,
                        "text/plain",
                        len(m["content"].encode("utf-8")),
                    ),
                )
                cur.execute(
                    "INSERT IGNORE INTO knowledge_entries (material_id, class_id, "
                    "content, source) VALUES (%s, %s, %s, %s)",
                    (m["id"], m["class_id"], m["content"], m["filename"]),
                )
    conn.commit()


def seed(conn: pymysql.connections.Connection, upload_root: Path | None = None) -> None:
    """Insert seed data (idempotent via INSERT IGNORE)."""
    if upload_root is None:
        upload_root = resolve_upload_root(os.environ.get("UPLOAD_ROOT", "uploads"), ROOT)

    # Pre-compute hashes once
    teacher_a_hash = hash_password("teacher_a_pass")
    teacher_b_hash = hash_password("teacher_b_pass")
    student_a_hash = hash_password("student_a_pass")
    student_b_hash = hash_password("student_b_pass")

    with conn.cursor() as cur:
        # Classes (explicit ids keep cross-class fixtures stable)
        cur.execute(
            "INSERT IGNORE INTO classes (id, name) VALUES (1, 'A班'), (2, 'B班')"
        )
        # Users with parameterized hashes
        users = [
            (1, "teacher_a", teacher_a_hash, "teacher", 1),
            (2, "teacher_b", teacher_b_hash, "teacher", 2),
            (3, "student_a", student_a_hash, "student", 1),
            (4, "student_b", student_b_hash, "student", 2),
        ]
        cur.executemany(
            "INSERT IGNORE INTO users (id, username, password_hash, role, class_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            users,
        )
    conn.commit()
    _seed_materials(conn, upload_root)


def _db_config_from_env() -> dict:
    return {
        "host": os.environ.get("DB_HOST", "db"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "app"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "campusclaw"),
    }


def main() -> None:
    cfg = _db_config_from_env()
    conn = get_connection(cfg)
    for name in MIGRATIONS:
        run_migration(conn, str(ROOT / "migrations" / name))
    seed(conn)

    # Verify
    with conn.cursor() as cur:
        for table in ("classes", "users", "materials", "knowledge_entries"):
            cur.execute(f"SELECT count(*) AS n FROM {table}")
            print(f"{table}: {cur.fetchone()['n']} rows")

        cur.execute(
            "SELECT m.class_id, m.filename FROM materials m ORDER BY m.class_id"
        )
        for t in cur.fetchall():
            print(f"  material class_id={t['class_id']} filename={t['filename']}")

    conn.close()
    print("Seed complete.")


if __name__ == "__main__":
    main()
