"""Async grading worker (lesson 8): consumes the MySQL jobs table.

Runs as its own container (`python -m app.worker`). Deliberately no Flask:
the worker reads config, opens its own connections and calls the gateway.
Claiming uses `FOR UPDATE SKIP LOCKED`; results and the job status are written
in one transaction so a replayed job can never produce a second result.

Environment knobs (all optional):
- WORKER_POLL_INTERVAL: idle sleep between polls, seconds (default 2)
- WORKER_STALE_LOCK_SECONDS: running jobs older than this are re-queued (60)
"""
import json
import signal
import sys
import time

import pymysql

from app.config import Config, ConfigError
from app.db.connection import get_connection
from app.repositories import grading as repo
from app.repositories import wrong_questions as wrong_questions_repo
from app.services import audit as audit_service
from app.services import grading as grading_service

DB_WAIT_SECONDS = 120

_stop = False


def _log(event: str, **fields) -> None:
    """Single-line JSON log; never carries tokens or gateway keys."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _handle_stop(signum, frame) -> None:  # noqa: ARG001
    global _stop
    _stop = True


def wait_for_db(db: dict) -> None:
    """Wait until MySQL answers and the jobs table exists (api migrates first)."""
    deadline = time.time() + DB_WAIT_SECONDS
    while time.time() < deadline:
        try:
            conn = get_connection(db)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM jobs LIMIT 1")
                return
            finally:
                conn.close()
        except pymysql.MySQLError as exc:
            _log("waiting_for_db", error=type(exc).__name__)
            time.sleep(2)
    raise RuntimeError("jobs table not reachable; api migrations not finished?")


def requeue_stale(db: dict, seconds: int) -> None:
    conn = get_connection(db)
    try:
        count = repo.requeue_stale(conn, seconds)
        conn.commit()
        if count:
            _log("requeued_stale", count=count)
    finally:
        conn.close()


def _fail(db: dict, job: dict, submission_id: int | None, reason: str) -> None:
    """Record a failed attempt; mirror the submission status when final."""
    conn = get_connection(db)
    try:
        new_status = repo.finish_job(conn, job["id"], "failed", reason)
        if submission_id is not None:
            if new_status == "failed":
                repo.finish_submission(conn, submission_id, None, reason, "failed")
            else:
                repo.set_submission_status(conn, submission_id, "pending")
        conn.commit()
    finally:
        conn.close()
    _log(
        "job_retry" if new_status == "pending" else "job_failed",
        jobId=job["id"],
        submissionId=submission_id,
        status=new_status,
        reason=reason,
    )


def _succeed(db: dict, job: dict, submission_id: int, score, feedback,
             elapsed_ms: float | None = None) -> None:
    conn = get_connection(db)
    wrong_question_id = None
    try:
        repo.finish_submission(conn, submission_id, score, feedback, "succeeded")
        # 判错（score < 60）时同事务写入错题；UNIQUE(submission_id) 让重放幂等。
        if score is not None and score < 60:
            wrong_question_id = wrong_questions_repo.upsert_from_submission(
                conn, submission_id, job["class_id"]
            )
        repo.finish_job(conn, job["id"], "succeeded")
        # SEC-07: the grade row shares the result transaction (skill + usage).
        audit_service.insert_commit(
            conn,
            class_id=job["class_id"],
            actor_id=None,
            action="grade",
            target_type="submission",
            target_id=submission_id,
            skill_name="作业批改",
            detail={
                "jobId": job["id"],
                "score": score,
                "ms": elapsed_ms,
                "wrongQuestionId": wrong_question_id,
            },
        )
        conn.commit()
    finally:
        conn.close()
    _log(
        "job_succeeded",
        jobId=job["id"],
        submissionId=submission_id,
        score=score,
        wrongQuestionId=wrong_question_id,
        ms=elapsed_ms,
    )


def run_once(db: dict, config: Config) -> bool:
    """Process at most one job. Returns True when a job was picked up."""
    conn = get_connection(db)
    submission_id = None
    try:
        job = repo.claim_next(conn)
        if job is None:
            conn.commit()
            return False
        submission_id = int((job.get("payload") or {}).get("submission_id"))
        repo.set_submission_status(conn, submission_id, "running")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    conn = get_connection(db)
    try:
        submission = repo.find_submission(conn, submission_id, job["class_id"])
        assignment = (
            repo.find_assignment(conn, submission["assignment_id"], job["class_id"])
            if submission is not None
            else None
        )
    finally:
        conn.close()

    if submission is None or assignment is None:
        _fail(db, job, submission_id, "提交或作业不存在")
        return True

    try:
        started = time.perf_counter()
        score, feedback = grading_service.grade(
            config,
            assignment["question"],
            assignment["reference_answer"],
            submission["answer"],
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    except grading_service.GradingFailed as exc:
        _fail(db, job, submission_id, str(exc))
        return True
    except Exception as exc:  # gateway unavailable/rejected → retry per policy
        _fail(db, job, submission_id, f"批改调用失败：{type(exc).__name__}")
        return True

    _succeed(db, job, submission_id, score, feedback, elapsed_ms=elapsed_ms)
    return True


def main() -> None:
    try:
        config = Config()
    except ConfigError as exc:
        print(f"Startup error: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    db = config.db_config()
    wait_for_db(db)
    requeue_stale(db, config.worker_stale_lock_seconds)
    _log("worker_started", pollInterval=config.worker_poll_interval)

    while not _stop:
        try:
            processed = run_once(db, config)
        except pymysql.MySQLError as exc:
            _log("db_error", error=type(exc).__name__)
            time.sleep(config.worker_poll_interval)
            continue
        if not processed:
            time.sleep(config.worker_poll_interval)

    _log("worker_stopped")


if __name__ == "__main__":
    main()
