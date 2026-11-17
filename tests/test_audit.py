"""SEC-07 audit logs: seven columns, queryable, class-scoped.

Covers normal (login / upload / assignment / submit / grade / explain rows),
failure (student 403 / unauth 401 / unknown filter 400) and boundary
(cross-class isolation, limit clamp, action filter).
"""
import io
import json

from app import worker
from app.config import Config
from app.services import model_gateway
from tests.conftest import query_all, query_one

ASSIGNMENT = {
    "title": "一元一次方程作业",
    "question": "解方程 2x + 3 = 11",
    "reference_answer": "x = 4",
}


def _rows(db, class_id=1):
    return query_all(
        db,
        "SELECT * FROM audit_logs WHERE class_id = %s ORDER BY id",
        (class_id,),
    )


def _actions(rows):
    return [(r["action"], r["target_type"]) for r in rows]


def _upload(client, name="audit.txt", content=b"audit body"):
    data = {"file": (io.BytesIO(content), name)}
    return client.post("/materials", data=data, content_type="multipart/form-data")


class TestAuditWrites:
    def test_login_writes_row(self, teacher_a, test_db):
        rows = _rows(test_db)
        assert ("login", "session") in _actions(rows)
        login = [r for r in rows if r["action"] == "login"][-1]
        assert login["actor_id"] == 1  # teacher_a
        assert login["class_id"] == 1
        assert "role" in json.loads(login["detail"])

    def test_logout_writes_row(self, teacher_a, test_db):
        teacher_a.post("/auth/logout")
        assert ("logout", "session") in _actions(_rows(test_db))

    def test_upload_writes_create_material(self, teacher_a, test_db):
        resp = _upload(teacher_a)
        assert resp.status_code == 201
        material_id = resp.get_json()["id"]
        row = query_one(
            test_db,
            "SELECT * FROM audit_logs WHERE action = 'create' AND target_type = 'material' "
            "AND target_id = %s",
            (material_id,),
        )
        assert row is not None
        assert row["actor_id"] == 1

    def test_assignment_and_submit_rows(self, teacher_a, student_a, test_db):
        resp = teacher_a.post("/api/assignments", json=ASSIGNMENT)
        assert resp.status_code == 201
        assignment_id = resp.get_json()["assignment"]["id"]
        sub = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x = 5"}
        )
        assert sub.status_code == 202
        submission_id = sub.get_json()["submissionId"]

        assignment_row = query_one(
            test_db,
            "SELECT * FROM audit_logs WHERE action = 'create' AND target_type = 'assignment'",
        )
        assert assignment_row["target_id"] == assignment_id
        submit_row = query_one(
            test_db,
            "SELECT * FROM audit_logs WHERE action = 'submit' AND target_type = 'submission'",
        )
        assert submit_row["target_id"] == submission_id
        assert submit_row["actor_id"] == 3  # student_a

    def test_grade_row_has_skill_and_usage(self, teacher_a, student_a, test_db,
                                           monkeypatch):
        resp = teacher_a.post("/api/assignments", json=ASSIGNMENT)
        assignment_id = resp.get_json()["assignment"]["id"]
        sub = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x = 5"}
        )
        submission_id = sub.get_json()["submissionId"]

        def _fake_chat(config, messages):
            return json.dumps({"score": 40, "feedback": "思路偏离"}, ensure_ascii=False)

        monkeypatch.setattr(model_gateway, "chat", _fake_chat)
        worker.run_once(test_db, Config())

        row = query_one(
            test_db,
            "SELECT * FROM audit_logs WHERE action = 'grade' AND target_id = %s",
            (submission_id,),
        )
        assert row is not None
        assert row["skill_name"] == "作业批改"
        detail = json.loads(row["detail"])
        assert detail["score"] == 40
        assert detail["ms"] is not None
        assert detail["wrongQuestionId"] is not None

    def test_explain_row(self, teacher_a, student_a, test_db, monkeypatch,
                         chat_stream_spy):
        resp = teacher_a.post("/api/assignments", json=ASSIGNMENT)
        assignment_id = resp.get_json()["assignment"]["id"]
        sub = student_a.post(
            f"/api/assignments/{assignment_id}/submissions", json={"answer": "x = 5"}
        )
        submission_id = sub.get_json()["submissionId"]

        monkeypatch.setattr(
            model_gateway, "chat",
            lambda config, messages: json.dumps(
                {"score": 30, "feedback": "错"}, ensure_ascii=False
            ),
        )
        worker.run_once(test_db, Config())
        wq = query_one(
            test_db,
            "SELECT id FROM wrong_questions WHERE submission_id = %s",
            (submission_id,),
        )
        assert student_a.post(f"/api/wrong-questions/{wq['id']}/explain").status_code == 200

        row = query_one(
            test_db,
            "SELECT * FROM audit_logs WHERE action = 'explain'",
        )
        assert row is not None
        assert row["target_type"] == "wrong_question"
        assert row["target_id"] == wq["id"]
        assert row["skill_name"] == "错题讲解"


class TestAuditAPI:
    def test_teacher_reads_own_class(self, teacher_a, test_db):
        resp = teacher_a.get("/api/audit-logs")
        assert resp.status_code == 200
        logs = resp.get_json()["audit_logs"]
        assert logs
        assert all(row["classId"] == 1 for row in logs)
        # seven SEC-07 columns are all present in the payload
        first = logs[0]
        for key in ("action", "targetType", "targetId", "actorId", "classId",
                    "skillName", "detail", "createdAt"):
            assert key in first

    def test_student_403(self, student_a):
        assert student_a.get("/api/audit-logs").status_code == 403

    def test_unauthenticated_401(self, app_client):
        assert app_client.get("/api/audit-logs").status_code == 401

    def test_cross_class_isolation(self, teacher_a, teacher_b, test_db):
        _upload(teacher_a, name="a-only.txt")
        b_logs = teacher_b.get("/api/audit-logs").get_json()["audit_logs"]
        # 每个班只能看到本班行；A 班的上传不会出现在 B 班
        assert all(row["classId"] == 2 for row in b_logs)
        assert not any(row["targetType"] == "material" for row in b_logs)

    def test_action_filter(self, teacher_a):
        _upload(teacher_a)
        resp = teacher_a.get("/api/audit-logs?action=create&target_type=material")
        assert resp.status_code == 200
        rows = resp.get_json()["audit_logs"]
        assert rows
        assert all(r["action"] == "create" and r["targetType"] == "material" for r in rows)

    def test_unknown_filter_400(self, teacher_a):
        assert teacher_a.get("/api/audit-logs?action=nope").status_code == 400
        assert teacher_a.get("/api/audit-logs?target_type=nope").status_code == 400

    def test_limit_clamped(self, teacher_a):
        for i in range(5):
            _upload(teacher_a, name=f"limit-{i}.txt")
        rows = teacher_a.get("/api/audit-logs?limit=2").get_json()["audit_logs"]
        assert len(rows) <= 2
        # over the max is clamped, not rejected
        assert teacher_a.get("/api/audit-logs?limit=9999").status_code == 200
