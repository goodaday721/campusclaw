"""Wrong questions (lesson 11 必做: 错题本 + 错题讲解技能).

Covers normal (low-score write / list / detail / explain), failure (high score
skips / cross-class 404 / cross-student 404 / unauthenticated 401), and
boundary (worker replay idempotent / skill seeded and bound).
"""
import json

import pytest

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


def _submit(client, assignment_id, answer="x = 5"):
    resp = client.post(
        f"/api/assignments/{assignment_id}/submissions", json={"answer": answer}
    )
    assert resp.status_code == 202, resp.get_json()
    return resp.get_json()["submissionId"]


def _run_worker_once(monkeypatch, test_db, score, feedback="思路偏离"):
    """Drive the worker end-to-end with a fake gateway result."""
    def _fake_chat(config, messages):
        return json.dumps({"score": score, "feedback": feedback}, ensure_ascii=False)

    monkeypatch.setattr(model_gateway, "chat", _fake_chat)
    config = Config()
    worker.run_once(test_db, config)


class TestWrongQuestionGeneration:
    def test_low_score_creates_row(self, teacher_a, student_a, test_db, monkeypatch):
        assignment_id = _create_assignment(teacher_a)
        submission_id = _submit(student_a, assignment_id)
        _run_worker_once(monkeypatch, test_db, score=40, feedback="未识别方程类型")

        row = query_one(
            test_db,
            "SELECT * FROM wrong_questions WHERE submission_id = %s",
            (submission_id,),
        )
        assert row is not None
        assert row["class_id"] == 1
        assert row["student_id"] == 3  # student_a seed id
        assert "2x + 3 = 11" in row["question"]
        assert row["student_answer"] == "x = 5"
        assert row["reference_answer"] == "x = 4"
        assert "未识别方程" in row["reason"]

    def test_high_score_skips(self, teacher_a, student_a, test_db, monkeypatch):
        assignment_id = _create_assignment(teacher_a)
        _submit(student_a, assignment_id, answer="x = 4")
        _run_worker_once(monkeypatch, test_db, score=85)

        row = query_one(test_db, "SELECT count(*) AS n FROM wrong_questions")
        assert row["n"] == 0

    def test_worker_replay_is_idempotent(
        self, teacher_a, student_a, test_db, monkeypatch
    ):
        assignment_id = _create_assignment(teacher_a)
        submission_id = _submit(student_a, assignment_id)
        _run_worker_once(monkeypatch, test_db, score=30)
        first = query_one(test_db, "SELECT count(*) AS n FROM wrong_questions")
        assert first["n"] == 1

        # Force the job back to pending and run again — UNIQUE(submission_id)
        # must swallow the second insert.
        execute(
            test_db,
            "UPDATE jobs SET status = 'pending' WHERE dedupe_key = %s",
            (f"grade:{submission_id}",),
        )
        _run_worker_once(monkeypatch, test_db, score=30)
        second = query_one(test_db, "SELECT count(*) AS n FROM wrong_questions")
        assert second["n"] == 1


class TestWrongQuestionSkillSeeded:
    def test_skill_registered_and_bound(self, test_db):
        for class_id in (1, 2):
            row = query_one(
                test_db,
                "SELECT id, enabled FROM skills WHERE class_id = %s AND name = %s",
                (class_id, "错题讲解"),
            )
            assert row is not None, f"class {class_id} missing 错题讲解"
            assert row["enabled"] == 1
            binding = query_one(
                test_db,
                "SELECT count(*) AS n FROM agent_skills WHERE skill_id = %s",
                (row["id"],),
            )
            assert binding["n"] >= 1, "错题讲解 not bound to any agent"


class TestWrongQuestionAPI:
    def _seed_one_wrong(self, teacher_a, student_a, test_db, monkeypatch, score=40):
        assignment_id = _create_assignment(teacher_a)
        submission_id = _submit(student_a, assignment_id)
        _run_worker_once(monkeypatch, test_db, score=score)
        return query_one(
            test_db,
            "SELECT id FROM wrong_questions WHERE submission_id = %s",
            (submission_id,),
        )["id"]

    def test_student_sees_own_list(
        self, teacher_a, student_a, test_db, monkeypatch
    ):
        wq_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = student_a.get("/api/wrong-questions")
        assert resp.status_code == 200
        rows = resp.get_json()["wrong_questions"]
        assert [r["id"] for r in rows] == [wq_id]
        assert rows[0]["studentId"] == 3

    def test_teacher_sees_class_list(
        self, teacher_a, student_a, test_db, monkeypatch
    ):
        wq_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = teacher_a.get("/api/wrong-questions")
        assert resp.status_code == 200
        rows = resp.get_json()["wrong_questions"]
        assert any(r["id"] == wq_id for r in rows)
        assert all(r["classId"] == 1 for r in rows)

    def test_cross_class_list_empty(
        self, teacher_a, student_a, student_b, test_db, monkeypatch
    ):
        self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = student_b.get("/api/wrong-questions")
        assert resp.status_code == 200
        assert resp.get_json()["wrong_questions"] == []

    def test_detail_owner_ok(self, teacher_a, student_a, test_db, monkeypatch):
        wq_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = student_a.get(f"/api/wrong-questions/{wq_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == wq_id
        assert "2x + 3 = 11" in body["question"]

    def test_detail_cross_class_isomorphic_404(
        self, teacher_a, student_a, student_b, test_db, monkeypatch
    ):
        wq_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        cross = student_b.get(f"/api/wrong-questions/{wq_id}")
        missing = student_b.get("/api/wrong-questions/99999")
        assert cross.status_code == 404
        assert missing.status_code == 404
        assert cross.get_json() == missing.get_json() == {"error": "not found"}

    def test_detail_cross_student_404(
        self, teacher_a, teacher_b, student_a, student_b, test_db, monkeypatch
    ):
        # B 班教师插一个 B 班学生错题，A 班学生来查 → 404
        a_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = student_b.get(f"/api/wrong-questions/{a_id}")
        assert resp.status_code == 404

    def test_unauthenticated_401(self, app_client):
        assert app_client.get("/api/wrong-questions").status_code == 401
        assert app_client.get("/api/wrong-questions/1").status_code == 401
        assert app_client.post("/api/wrong-questions/1/explain").status_code == 401


class TestWrongQuestionExplain:
    def _seed_one_wrong(self, teacher_a, student_a, test_db, monkeypatch):
        assignment_id = _create_assignment(teacher_a)
        submission_id = _submit(student_a, assignment_id)
        _run_worker_once(monkeypatch, test_db, score=40)
        return query_one(
            test_db,
            "SELECT id FROM wrong_questions WHERE submission_id = %s",
            (submission_id,),
        )["id"]

    def test_explain_streams_and_records_conversation(
        self, teacher_a, student_a, test_db, monkeypatch, chat_stream_spy
    ):
        wq_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = student_a.post(f"/api/wrong-questions/{wq_id}/explain")
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        body = resp.get_data(as_text=True)
        assert "data:" in body  # SSE format

        # 讲解对话被持久化
        conv = query_one(
            test_db,
            "SELECT id, agent_id, user_id FROM conversations "
            "WHERE user_id = 3 ORDER BY id DESC LIMIT 1",
        )
        assert conv is not None
        user_msg = query_one(
            test_db,
            "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user'",
            (conv["id"],),
        )
        assert "2x + 3 = 11" in user_msg["content"]
        assert "参考答案" in user_msg["content"]

    def test_explain_cross_class_404(
        self, teacher_a, student_a, student_b, test_db, monkeypatch
    ):
        wq_id = self._seed_one_wrong(teacher_a, student_a, test_db, monkeypatch)
        resp = student_b.post(f"/api/wrong-questions/{wq_id}/explain")
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "not found"}

    def test_explain_missing_404(self, student_a):
        resp = student_a.post("/api/wrong-questions/99999/explain")
        assert resp.status_code == 404
