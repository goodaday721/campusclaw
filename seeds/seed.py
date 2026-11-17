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
    "005_mcp.sql",
    "006_grading.sql",
    "007_wrong_questions.sql",
    "008_audit_logs.sql",
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

# Lesson 11 拓展：关怀式对话。只在学生表达挫败/焦虑时由 chat 管线注入
# （见 app.services.chat.needs_care），与错题讲解并列绑定到默认助手。
SEED_CARE_SKILL = {
    "source": (
        "名称：关怀式对话\n"
        "适用条件：学生表达挫败、焦虑、想放弃等情绪\n"
        "资料：数学\n"
        "启用：是\n"
        "\n"
        "你是“关怀式对话”技能。当学生流露出挫败或焦虑时，你必须：\n"
        "1. 先用一句话承认他的感受，不做评判，也不急着讲题；\n"
        "2. 具体指出他已经做对的部分，或指出这道题本身确实容易卡住的地方；\n"
        "3. 把目标缩小成一个 5 分钟内能完成的小步骤，邀请他先试这一步；\n"
        "4. 语气温和、句子短，不使用“你应该”“这么简单”等否定式表达；\n"
        "5. 学生情绪缓和后，再回到正常解题引导。"
    ),
}

# Lesson 11 必做: 错题讲解技能。绑定到本班默认解题助手，由
# `POST /api/wrong-questions/<id>/explain` 触发的对话激活。
SEED_WRONG_QUESTION_SKILL = {
    "name": "错题讲解",
    "trigger": "已判错的题、错题本、错题讲解",
    "tools": ["knowledge_search"],
    "subject": "数学",
    "source": (
        "名称：错题讲解\n"
        "适用条件：学生请求讲解一道已判错的题\n"
        "工具：knowledge_search\n"
        "资料：数学\n"
        "启用：是\n"
        "\n"
        "你是“错题讲解”技能。面对一道判错的题，你必须：\n"
        "1. 先诊断错因类型：概念不清 / 计算失误 / 审题偏差 / 思路方向错误，"
        "用一句话点明；\n"
        "2. 指出学生答案里**具体哪一步**开始偏离；\n"
        "3. 用提问方式引导学生自己发现正确路径，每次只问一个引导问题；\n"
        "4. 学生给出新思路后再确认或继续引导；\n"
        "5. 全程不直接给最终答案；学生推出正确答案后再让其对照参考答案验证。"
    ),
}

# Lesson 6 seed: pre-register one MCP tool server per class (disconnected).
# The token comes from the MCP_AUTH_TOKEN env var (same value the mcp-demo
# container runs with); seeding SKIPS registration when it is unset so test
# environments without the tool server stay clean. Connection is a deliberate
# teacher action (startup must not depend on mcp-demo being ready).
SEED_MCP_SERVER = {"name": "campus-tools", "base_url": "http://mcp-demo:8090"}

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
    _seed_extra_skill(conn, SEED_WRONG_QUESTION_SKILL)
    _seed_extra_skill(conn, SEED_CARE_SKILL)


def _seed_extra_skill(conn: pymysql.connections.Connection, spec: dict) -> None:
    """Register one extra built-in skill on both classes and bind the default agent."""
    import json

    from app.services.skill_source import parse

    fields = parse(spec["source"])
    tools_json = json.dumps(fields.get("tools") or [], ensure_ascii=False)
    with conn.cursor() as cur:
        for class_id in SEED_CLASS_PROMPTS:
            cur.execute(
                "SELECT id FROM skills WHERE class_id = %s AND name = %s",
                (class_id, fields["name"]),
            )
            if cur.fetchone() is not None:
                continue
            cur.execute(
                "INSERT INTO skills (class_id, name, `trigger`, tools, subject, "
                "description, source, enabled) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
                (
                    class_id,
                    fields["name"],
                    fields.get("trigger", ""),
                    tools_json,
                    fields.get("subject", ""),
                    fields["description"],
                    spec["source"],
                ),
            )
            skill_id = cur.lastrowid
            # Bind to the default enabled agent (created above by _seed_assistant).
            cur.execute(
                "SELECT id FROM agents WHERE class_id = %s AND name = %s AND enabled = 1 "
                "ORDER BY id LIMIT 1",
                (class_id, SEED_AGENT_NAME),
            )
            agent_row = cur.fetchone()
            if agent_row is not None:
                cur.execute(
                    "INSERT IGNORE INTO agent_skills (agent_id, skill_id) VALUES (%s, %s)",
                    (agent_row["id"], skill_id),
                )
    conn.commit()


def _seed_mcp_servers(conn: pymysql.connections.Connection) -> None:
    """Pre-register one MCP tool server per class (idempotent, disconnected)."""
    token = (os.environ.get("MCP_AUTH_TOKEN") or "").strip()
    if not token:
        return
    with conn.cursor() as cur:
        for class_id in SEED_CLASS_PROMPTS:
            cur.execute(
                "SELECT id FROM mcp_servers WHERE class_id = %s AND name = %s",
                (class_id, SEED_MCP_SERVER["name"]),
            )
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO mcp_servers (class_id, name, base_url, token) "
                    "VALUES (%s, %s, %s, %s)",
                    (class_id, SEED_MCP_SERVER["name"], SEED_MCP_SERVER["base_url"], token),
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
    _seed_mcp_servers(conn)


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
