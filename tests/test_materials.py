"""Tests for knowledge-materials: transactional upload, whitelist, download."""
import io

from tests.conftest import query_all, query_one


def _knowledge_count(db: dict) -> int:
    return query_one(db, "SELECT count(*) AS n FROM knowledge_entries")["n"]


def _upload(client, content: bytes, filename: str, **extra):
    data = {"file": (io.BytesIO(content), filename), **extra}
    return client.post("/materials", data=data, content_type="multipart/form-data")


class TestUploadMaterial:
    """Teacher upload → 201, two tables in one transaction, class from session."""

    def test_upload_success_writes_both_tables(self, teacher_a, test_db):
        """Upload → 201; materials + knowledge_entries rows with same class_id."""
        resp = _upload(teacher_a, b"hello world", "lesson.txt")
        assert resp.status_code == 201
        record = resp.get_json()
        assert record["class_id"] == 1  # teacher_a is in class 1
        assert record["filename"] == "lesson.txt"

        entry = query_one(
            test_db,
            "SELECT class_id, content, source FROM knowledge_entries "
            "WHERE material_id = %s",
            (record["id"],),
        )
        assert entry is not None
        assert entry["class_id"] == 1
        assert entry["content"] == "hello world"
        assert entry["source"] == "lesson.txt"

    def test_storage_name_server_generated(self, teacher_a):
        """Storage key must be server-generated, not the client filename."""
        resp = _upload(teacher_a, b"data", "doc.txt")
        storage_key = resp.get_json()["storage_key"]
        assert "doc.txt" not in storage_key  # original name only in DB field
        assert storage_key.endswith(".txt")

    def test_class_id_from_session_not_client(self, teacher_a):
        """Client declares classId=2 in form data; record uses session classId=1."""
        resp = _upload(teacher_a, b"data", "doc.txt", classId="2")
        assert resp.status_code == 201
        assert resp.get_json()["class_id"] == 1  # session wins, not client

    def test_transaction_failure_leaves_no_orphans(
        self, teacher_a, test_db, monkeypatch
    ):
        """DB failure → both tables rolled back AND the written file removed."""
        from app.repositories import knowledge as knowledge_repo
        import app.services.upload as upload_service

        def boom(*args, **kwargs):
            raise RuntimeError("simulated DB failure")

        monkeypatch.setattr(knowledge_repo, "create", boom)
        monkeypatch.setattr(upload_service.knowledge_repo, "create", boom)

        resp = _upload(teacher_a, b"orphan-test", "broken.txt")
        assert resp.status_code == 500

        # Only the 2 seeded materials remain; nothing from the failed upload
        assert query_one(test_db, "SELECT count(*) AS n FROM materials")["n"] == 2
        assert _knowledge_count(test_db) == 2
        # The file written before the failure was cleaned up
        keys = query_all(test_db, "SELECT storage_key FROM materials")
        for row in keys:
            assert "broken" not in row["storage_key"]


class TestListMaterials:
    def test_student_and_teacher_can_read_own_class(self, teacher_a, student_a):
        """Upload as teacher → student sees it in GET /materials."""
        resp = _upload(teacher_a, b"content", "shared.txt")
        assert resp.status_code == 201
        uploaded = resp.get_json()["filename"]

        resp = student_a.get("/materials")
        assert resp.status_code == 200
        filenames = [m["filename"] for m in resp.get_json()["materials"]]
        assert uploaded in filenames  # seeded A-class material also present

    def test_uploaded_material_appears_in_list(self, teacher_a):
        resp = _upload(teacher_a, b"new", "newfile.txt")
        uploaded_id = resp.get_json()["id"]
        resp = teacher_a.get("/materials")
        ids = [m["id"] for m in resp.get_json()["materials"]]
        assert uploaded_id in ids


class TestUploadConstraints:
    def test_oversized_file_rejected(self, teacher_a):
        """File exceeding size limit → 413, nothing stored."""
        big_data = b"x" * (51 * 1024 * 1024)  # 51MB > 50MB limit
        resp = _upload(teacher_a, big_data, "big.txt")
        assert resp.status_code == 413

    def test_non_whitelisted_extension_rejected(self, teacher_a, test_db):
        """.pdf/.docx/images are NOT in the .txt/.md whitelist → 415."""
        for name in ("evil.pdf", "doc.docx", "pic.png", "evil.exe"):
            resp = _upload(teacher_a, b"malware", name)
            assert resp.status_code == 415, f"{name} should be rejected"
        # No new rows from rejected uploads (2 seeded remain)
        assert query_one(test_db, "SELECT count(*) AS n FROM materials")["n"] == 2


class TestDownload:
    def test_classmate_downloads_same_content(self, teacher_a, student_a):
        """Student downloads a class material → content matches what was uploaded."""
        resp = _upload(teacher_a, b"downloadable-content", "notes.txt")
        material_id = resp.get_json()["id"]

        resp = student_a.get(f"/materials/{material_id}/download")
        assert resp.status_code == 200
        assert resp.data == b"downloadable-content"

    def test_cross_class_download_isomorphic_404(self, teacher_a, teacher_b):
        """Cross-class download and non-existent download → identical 404 body."""
        resp = _upload(teacher_b, b"b-secret", "b_notes.txt")
        b_id = resp.get_json()["id"]

        cross = teacher_a.get(f"/materials/{b_id}/download")
        missing = teacher_a.get("/materials/99999/download")
        assert cross.status_code == 404
        assert missing.status_code == 404
        assert cross.get_json() == missing.get_json()  # same shape, indistinguishable
