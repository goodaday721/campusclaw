"""Repository for wrong_questions (lesson 11 必做: 错题本).

Every read is class-scoped; student reads additionally filter by student_id so
cross-class and cross-student access both collapse to "not found" (the caller
returns 404). Writes go through `upsert_from_submission`, which JOINs the
submission with its assignment and inserts the denormalized row inside the
caller's transaction — UNIQUE(submission_id) makes worker replays idempotent.
"""

_COLS = (
    "id, class_id, submission_id, student_id, question, student_answer, "
    "reference_answer, reason, created_at"
)


def upsert_from_submission(conn, submission_id: int, class_id: int) -> int | None:
    """Insert (or refresh) the wrong_question row for a failed submission.

    Called by the worker inside the same transaction that finishes the
    submission. Returns the wrong_question id on insert, None when the
    submission or its assignment is missing.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id AS submission_id, s.class_id, s.student_id, s.answer, "
            "       s.feedback, a.question, a.reference_answer "
            "FROM submissions s "
            "JOIN assignments a ON a.id = s.assignment_id "
            "WHERE s.id = %s AND s.class_id = %s",
            (submission_id, class_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        reason = (row.get("feedback") or "").strip()[:200] or "答案错误"
        cur.execute(
            "INSERT INTO wrong_questions "
            "(class_id, submission_id, student_id, question, student_answer, "
            " reference_answer, reason) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "  reason = VALUES(reason), "
            "  student_answer = VALUES(student_answer)",
            (
                row["class_id"],
                row["submission_id"],
                row["student_id"],
                row["question"],
                row["answer"],
                row["reference_answer"],
                reason,
            ),
        )
        return int(cur.lastrowid) or None


def list_for_student(conn, student_id: int, class_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM wrong_questions "
            "WHERE class_id = %s AND student_id = %s ORDER BY id DESC",
            (class_id, student_id),
        )
        return cur.fetchall()


def list_for_class(conn, class_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM wrong_questions "
            "WHERE class_id = %s ORDER BY id DESC",
            (class_id,),
        )
        return cur.fetchall()


def find_by_id_scoped(
    conn, wq_id: int, class_id: int, student_id: int | None = None
) -> dict | None:
    """Class-scoped read; pass student_id to also enforce ownership.

    Returns None when the row is missing, in another class, or (when
    student_id is given) owned by someone else — the caller turns that into
    an isomorphic 404.
    """
    sql = f"SELECT {_COLS} FROM wrong_questions WHERE id = %s AND class_id = %s"
    params: list = [wq_id, class_id]
    if student_id is not None:
        sql += " AND student_id = %s"
        params.append(student_id)
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchone()
