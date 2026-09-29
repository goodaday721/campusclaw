"""Tests for role-access: student upload 403 before any write, teacher accepted."""
import io

from tests.conftest import query_one


def _upload(client, content: bytes, filename: str):
    return client.post(
        "/materials",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


class TestRoleRequired:
    def test_student_upload_returns_403(self, student_a, test_db):
        """Student calling POST /materials → 403, no file, no rows."""
        resp = _upload(student_a, b"test", "test.txt")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "forbidden"

        count = query_one(test_db, "SELECT count(*) AS n FROM materials")["n"]
        assert count == 2  # only the two seeded materials

    def test_teacher_upload_accepted(self, teacher_a):
        """Teacher calling POST /materials → proceeds (201)."""
        resp = _upload(teacher_a, b"hello", "test.txt")
        assert resp.status_code == 201  # not 403


class TestBypassFrontend:
    def test_student_bypass_frontend_still_403(self, student_a):
        """Student using session cookie directly (no frontend UI) → still 403."""
        resp = student_a.post(
            "/materials",
            headers={"Accept": "application/json"},
            data={"file": (io.BytesIO(b"hacked"), "hack.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 403
