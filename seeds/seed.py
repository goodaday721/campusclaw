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
    "004_assistant.sql",
]

# Lesson 5 seeds: one class prompt + one guided skill + one enabled agent per
# class, so the assistant demo works out of the box (material_ids empty =
# the agent searches the whole class library).
SEED_CLASS_PROMPTS = {
    1: (
        "A班解题助手：你是本班的解题引导老师。回答必须依据本班资料切片，"
        "每条结论后用 [序号] 标注出处。你的职责是引导学生自己思考："
        "先确认学生对题目的理解，再逐步提示思路，绝不直接给出最终答案。"
        "回答使用简体中文，保持简短。"
    ),
    2: (
        "B班解题助手：你是本班的解题引导老师。回答必须依据本班资料切片，"
        "每条结论后用 [序号] 标注出处。你的职责是引导学生自己思考："
        "先确认学生对题目的理解，再逐步提示思路，绝不直接给出最终答案。"
        "回答使用简体中文，保持简短。"
    ),
}

SEED_SKILL = {
    "name": "方程解题引导",
    "trigger": "一元一次方程、二元一次方程组",
    "tools": ["knowledge_search"],
    "subject": "数学",
    "source": (
        "名称：方程解题引导\n"
        "适用条件：一元一次方程、二元一次方程组\n"
        "工具：knowledge_search\n"
        "资料：数学\n"
        "启用：是\n"
        "\n"
        "你是“方程解题引导”技能。学生提问方程类问题时，你必须：\n"
        "1. 先请学生复述题目中的已知条件与未知量，确认理解无误；\n"
        "2. 每次只提示下一步该做什么（如“移项”“合并同类项”），"
        "不直接给出最终答案；\n"
        "3. 学生某一步答对时给予肯定并引导下一步；答错时追问其思路，"
        "指出卡点所在；\n"
        "4. 学生自己算出最终答案后，请其代入原方程检验。"
    ),
}

SEED_AGENT_NAME = "解题助手"

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


def _parse_seed_skill_source() -> dict:
    """Parse SEED_SKILL source with the same service the API uses (single source of truth)."""
    import json

    from app.services.skill_source import parse

    fields = parse(SEED_SKILL["source"])
    fields["tools"] = json.dumps(fields.get("tools") or [], ensure_ascii=False)
    return fields


def _seed_assistant(conn: pymysql.connections.Connection) -> None:
    """Insert class prompts, one guided skill and one enabled agent per class."""
    with conn.cursor() as cur:
        for class_id, body in SEED_CLASS_PROMPTS.items():
            cur.execute(
                "INSERT IGNORE INTO class_prompts (class_id, body) VALUES (%s, %s)",
                (class_id, body),
            )
    conn.commit()

    fields = _parse_seed_skill_source()
    with conn.cursor() as cur:
        for class_id in SEED_CLASS_PROMPTS:
            cur.execute(
                "SELECT id FROM skills WHERE class_id = %s AND name = %s",
                (class_id, fields["name"]),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO skills (class_id, name, `trigger`, tools, subject, "
                    "description, source, enabled) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
                    (
                        class_id,
                        fields["name"],
                        fields.get("trigger", ""),
                        fields["tools"],
                        fields.get("subject", ""),
                        fields["description"],
                        SEED_SKILL["source"],
                    ),
                )
                skill_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO agents (class_id, name, prompt, enabled) "
                    "VALUES (%s, %s, NULL, 1)",
                    (class_id, SEED_AGENT_NAME),
                )
                agent_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO agent_skills (agent_id, skill_id) VALUES (%s, %s)",
                    (agent_id, skill_id),
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
    _seed_assistant(conn)


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
