"""Lesson 8: assignments, submissions and the async grading worker.

Covers normal (create/submit/grade), failure (auth, validation, gateway retry)
and boundary (cross-class 404, idempotent resubmit, max attempts, stale lock).
"""
import json

from app import worker
from app.config import Config
from app.services import model_gateway
from tests.conftest import execute, query_one

ASSIGNMENT = {
    "title": "一元一次方程作业",
    "question": "解方程 2x + 3 = 11",
    "reference_answer": "x = 4",
}


def _create_assignment(client, **overrides):
    body = {**ASSIGNMENT, **overrides}
    resp = client.post("/api/assignments", json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["assignment"]["id"]


class TestAssignmentsAPI:
    def test_teacher_creates_and_lists(self, teacher_a):
        assignment_id = _create_assignment(teacher_a)
        resp = teacher_a.get("/api/assignments")
        assert resp.status_code == 200
        rows = resp.get_json()["assignments"]
        assert any(a["id"] == assignment_id for a in rows)
        assert rows[0]["classId"] == 1

    def test_student_cannot_create(self, student_a, test_db):
        resp = student_a.post("/api/assignments", json=ASSIGNMENT)
        assert resp.status_code == 403
        assert query_one(
            test_db, "SELECT count(*) AS n FROM assignments"
        )["n"] == 0

    def test_missing_fields_400(self, teacher_a):
        resp = teacher_a.post("/api/assignments", json={"title": "只有标题"})
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_unauthenticated_401(self, app_client):
        assert app_client.get("/api/assignments").status_code == 401
        assert app_client.post("/api/assignments", json=ASSIGNMENT).status_code == 401


class TestSubmissionsAPI:
    def test_student_submit_202_and_task(self, teacher_a, student_a, test_db):
        assignment_id = _create_assignment(teacher_a)
        resp = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=4"}
        )
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "pending"
        job = query_one(test_db, "SELECT * FROM jobs WHERE id = %s", (body["taskId"],))
        assert job["status"] == "pending"
        assert json.loads(job["payload"])["submission_id"] == body["submissionId"]

    def test_resubmit_is_idempotent(self, teacher_a, student_a, test_db):
        assignment_id = _create_assignment(teacher_a)
        first = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=4"}
        ).get_json()
        second = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=5"}
        ).get_json()
        assert first["taskId"] == second["taskId"]
        assert first["submissionId"] == second["submissionId"]
        assert query_one(test_db, "SELECT count(*) AS n FROM submissions")["n"] == 1
        assert query_one(test_db, "SELECT count(*) AS n FROM jobs")["n"] == 1

    def test_cross_class_submit_isomorphic_404(self, teacher_a, student_b):
        assignment_id = _create_assignment(teacher_a)
        resp = student_b.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=4"}
        )
        assert resp.status_code == 404

    def test_teacher_cannot_submit(self, teacher_a):
        assignment_id = _create_assignment(teacher_a)
        resp = teacher_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=4"}
        )
        assert resp.status_code == 403

    def test_empty_answer_400(self, teacher_a, student_a):
        assignment_id = _create_assignment(teacher_a)
        resp = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "  "}
        )
        assert resp.status_code == 400

    def test_missing_assignment_404(self, student_a):
        resp = student_a.post(
            "/api/assignments/999999/submissions", json={"answer": "x=4"}
        )
        assert resp.status_code == 404

    def test_unauthenticated_401(self, app_client):
        resp = app_client.post(
            "/api/assignments/1/submissions", json={"answer": "x=4"}
        )
        assert resp.status_code == 401


class TestPollingAPI:
    def _submit(self, teacher, student):
        assignment_id = _create_assignment(teacher)
        resp = student.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=4"}
        )
        return resp.get_json()

    def test_owner_student_polls_pending(self, teacher_a, student_a):
        body = self._submit(teacher_a, student_a)
        resp = student_a.get(f"/api/submissions/{body['submissionId']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "pending"
        assert data["taskId"] == body["taskId"]

    def test_other_student_404(self, teacher_a, student_a, student_b):
        body = self._submit(teacher_a, student_a)
        assert student_b.get(
            f"/api/submissions/{body['submissionId']}"
        ).status_code == 404

    def test_teacher_can_view_class_submission(self, teacher_a, student_a):
        body = self._submit(teacher_a, student_a)
        resp = teacher_a.get(f"/api/submissions/{body['submissionId']}")
        assert resp.status_code == 200

    def test_cross_class_teacher_404(self, teacher_a, student_a, teacher_b):
        body = self._submit(teacher_a, student_a)
        assert teacher_b.get(
            f"/api/submissions/{body['submissionId']}"
        ).status_code == 404

    def test_missing_submission_404(self, student_a):
        assert student_a.get("/api/submissions/999999").status_code == 404


class TestWorker:
    def _submit(self, teacher, student):
        assignment_id = _create_assignment(teacher)
        return student.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x=4"}
        ).get_json()

    def test_worker_grades_submission(self, teacher_a, student_a, test_db, monkeypatch):
        body = self._submit(teacher_a, student_a)
        monkeypatch.setattr(
            model_gateway, "chat",
            lambda config, messages: '{"score": 85, "feedback": "步骤清晰，注意检验。"}',
        )
        config = Config()
        assert worker.run_once(config.db_config(), config) is True

        sub = query_one(
            test_db, "SELECT * FROM submissions WHERE id = %s", (body["submissionId"],)
        )
        job = query_one(test_db, "SELECT * FROM jobs WHERE id = %s", (body["taskId"],))
        assert sub["status"] == "succeeded"
        assert sub["score"] == 85
        assert sub["feedback"] == "步骤清晰，注意检验。"
        assert job["status"] == "succeeded"
        assert worker.run_once(config.db_config(), config) is False

    def test_replayed_job_keeps_first_result(
        self, teacher_a, student_a, test_db, monkeypatch
    ):
        body = self._submit(teacher_a, student_a)
        replies = iter([
            '{"score": 85, "feedback": "第一次"}',
            '{"score": 60, "feedback": "第二次"}',
        ])
        monkeypatch.setattr(model_gateway, "chat", lambda config, messages: next(replies))
        config = Config()
        worker.run_once(config.db_config(), config)
        # Simulate at-least-once delivery: the same job is handed out again.
        execute(
            test_db,
            "UPDATE jobs SET status = 'pending', locked_at = NULL WHERE id = %s",
            (body["taskId"],),
        )
        worker.run_once(config.db_config(), config)
        sub = query_one(
            test_db, "SELECT * FROM submissions WHERE id = %s", (body["submissionId"],)
        )
        assert sub["score"] == 85
        assert sub["feedback"] == "第一次"

    def test_gateway_failure_retries_then_fails(
        self, teacher_a, student_a, test_db, monkeypatch
    ):
        body = self._submit(teacher_a, student_a)

        def _boom(config, messages):
            raise model_gateway.GatewayUnavailable("down")

        monkeypatch.setattr(model_gateway, "chat", _boom)
        config = Config()
        for _ in range(3):
            assert worker.run_once(config.db_config(), config) is True

        job = query_one(test_db, "SELECT * FROM jobs WHERE id = %s", (body["taskId"],))
        sub = query_one(
            test_db, "SELECT * FROM submissions WHERE id = %s", (body["submissionId"],)
        )
        assert job["status"] == "failed"
        assert job["attempts"] == 3
        assert job["last_error"]
        assert sub["status"] == "failed"
        assert sub["score"] is None
        assert worker.run_once(config.db_config(), config) is False

    def test_free_text_answer_degrades_gracefully(
        self, teacher_a, student_a, test_db, monkeypatch
    ):
        body = self._submit(teacher_a, student_a)
        monkeypatch.setattr(
            model_gateway, "chat", lambda config, messages: "过程完整，结论正确。"
        )
        config = Config()
        worker.run_once(config.db_config(), config)
        sub = query_one(
            test_db, "SELECT * FROM submissions WHERE id = %s", (body["submissionId"],)
        )
        assert sub["status"] == "succeeded"
        assert sub["score"] is None
        assert sub["feedback"] == "过程完整，结论正确。"

    def test_stale_running_job_is_requeued(self, test_db):
        execute(
            test_db,
            "INSERT INTO jobs (class_id, kind, dedupe_key, payload, status, locked_at) "
            "VALUES (1, 'grade', 'stale-test', %s, 'running', "
            "UTC_TIMESTAMP() - INTERVAL 120 SECOND)",
            (json.dumps({"submission_id": 999}),),
        )
        worker.requeue_stale(Config().db_config(), 60)
        row = query_one(test_db, "SELECT * FROM jobs WHERE dedupe_key = 'stale-test'")
        assert row["status"] == "pending"
        assert row["locked_at"] is None
