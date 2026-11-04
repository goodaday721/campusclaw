"""Repository for lesson-8 assignments, submissions and the jobs queue.

Every read helper takes a class_id (and, where ownership matters, a user id)
so cross-class ids can never leak. All SQL is parameterized; callers own the
transaction and decide when to commit.
"""
import json

_ASSIGNMENT_COLS = (
    "id, class_id, title, question, reference_answer, created_by, created_at"
)
_SUBMISSION_COLS = (
    "id, assignment_id, class_id, student_id, answer, status, score, feedback, "
    "graded_at, created_at, updated_at"
)
_JOB_COLS = (
    "id, class_id, kind, dedupe_key, payload, status, attempts, max_attempts, "
    "last_error, locked_at, created_at, updated_at"
)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

def list_assignments(conn, class_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_ASSIGNMENT_COLS} FROM assignments "
            "WHERE class_id = %s ORDER BY id DESC",
            (class_id,),
        )
        return cur.fetchall()


def find_assignment(conn, assignment_id: int, class_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_ASSIGNMENT_COLS} FROM assignments "
            "WHERE id = %s AND class_id = %s",
            (assignment_id, class_id),
        )
        return cur.fetchone()


def create_assignment(
    conn, class_id: int, title: str, question: str,
    reference_answer: str, created_by: int,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO assignments "
            "(class_id, title, question, reference_answer, created_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (class_id, title, question, reference_answer, created_by),
        )
        return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------

def find_submission(conn, submission_id: int, class_id: int) -> dict | None:
    """Class-scoped read; ownership is enforced by the caller."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SUBMISSION_COLS} FROM submissions "
            "WHERE id = %s AND class_id = %s",
            (submission_id, class_id),
        )
        return cur.fetchone()


def list_submissions(conn, class_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SUBMISSION_COLS} FROM submissions "
            "WHERE class_id = %s ORDER BY id DESC",
            (class_id,),
        )
        return cur.fetchall()


def upsert_submission(
    conn, assignment_id: int, class_id: int, student_id: int, answer: str,
) -> tuple[int, bool]:
    """Insert a submission, or return the existing one for (assignment, student).

    The UNIQUE(assignment_id, student_id) key is the idempotency anchor: a
    repeated submit keeps the FIRST answer and its single result.
    Returns (submission_id, created).
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO submissions (assignment_id, class_id, student_id, answer) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
            (assignment_id, class_id, student_id, answer),
        )
        created = cur.rowcount == 1
        return int(cur.lastrowid), created


def set_submission_status(conn, submission_id: int, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE submissions SET status = %s WHERE id = %s",
            (status, submission_id),
        )


def finish_submission(
    conn, submission_id: int, score: int | None, feedback: str | None,
    status: str,
) -> int:
    """Write the grading result once; a replayed job keeps the first result."""
    with conn.cursor() as cur:
        if status == "succeeded":
            cur.execute(
                "UPDATE submissions SET status = 'succeeded', score = %s, "
                "feedback = %s, graded_at = UTC_TIMESTAMP() "
                "WHERE id = %s AND graded_at IS NULL",
                (score, feedback, submission_id),
            )
        else:
            cur.execute(
                "UPDATE submissions SET status = 'failed', feedback = %s "
                "WHERE id = %s AND graded_at IS NULL",
                (feedback, submission_id),
            )
        return cur.rowcount


# ---------------------------------------------------------------------------
# Jobs (the queue)
# ---------------------------------------------------------------------------

def _job_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    row = dict(row)
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            row["payload"] = json.loads(payload)
        except ValueError:
            row["payload"] = {}
    return row


def find_job(conn, job_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_JOB_COLS} FROM jobs WHERE id = %s", (job_id,))
        return _job_row(cur.fetchone())


def find_job_by_dedupe(conn, dedupe_key: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_JOB_COLS} FROM jobs WHERE dedupe_key = %s",
            (dedupe_key,),
        )
        return _job_row(cur.fetchone())


def enqueue(
    conn, class_id: int, kind: str, dedupe_key: str,
    payload: dict, max_attempts: int = 3,
) -> int:
    """Insert one job; a duplicate dedupe_key reuses the existing task.

    The UNIQUE index + LAST_INSERT_ID trick makes this safe under concurrent
    submits: the loser of the race gets the winner's job id instead of 1062.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (class_id, kind, dedupe_key, payload, max_attempts) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
            (class_id, kind, dedupe_key, json.dumps(payload), max_attempts),
        )
        return int(cur.lastrowid)


def claim_next(conn) -> dict | None:
    """Claim one pending job (SKIP LOCKED) and mark it running.

    The caller MUST commit right after: until it does, the row lock keeps
    other consumers away and the job stays visible as pending.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_JOB_COLS} FROM jobs WHERE status = 'pending' "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            "UPDATE jobs SET status = 'running', locked_at = UTC_TIMESTAMP() "
            "WHERE id = %s",
            (row["id"],),
        )
    row = dict(row)
    row["status"] = "running"
    return _job_row(row)


def requeue_stale(conn, seconds: int = 60) -> int:
    """Recover jobs whose worker died while holding them → pending."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'pending', locked_at = NULL "
            "WHERE status = 'running' "
            "AND locked_at < UTC_TIMESTAMP() - INTERVAL %s SECOND",
            (int(seconds),),
        )
        return cur.rowcount


def finish_job(conn, job_id: int, status: str, error: str | None = None) -> str:
    """Close a running job; replayed/duplicate executions affect no other row.

    Returns the job status after the call (succeeded / pending / failed) so the
    worker can mirror it onto the submission.
    """
    if status == "succeeded":
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = 'succeeded', locked_at = NULL, "
                "last_error = NULL WHERE id = %s AND status = 'running'",
                (job_id,),
            )
        return "succeeded"
    with conn.cursor() as cur:
        cur.execute("SELECT attempts, max_attempts FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
        if row is None:
            return "failed"
        attempts = int(row["attempts"]) + 1
        final = attempts >= int(row["max_attempts"])
        new_status = "failed" if final else "pending"
        cur.execute(
            "UPDATE jobs SET status = %s, attempts = %s, last_error = %s, "
            "locked_at = NULL WHERE id = %s AND status = 'running'",
            (new_status, attempts, (error or "")[:255] or None, job_id),
        )
        return new_status
