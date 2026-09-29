"""Tests for class-isolation: session-scoped filtering, cross-class rejection."""
import io


def _upload(client, content: bytes, filename: str):
    return client.post(
        "/materials",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


class TestMaterialsRepository:
    def test_find_by_class_returns_only_class_materials(self, test_db):
        from app.db.connection import get_connection
        from app.repositories.materials import MaterialsRepository

        conn = get_connection(test_db)
        repo = MaterialsRepository(conn)
        # Seeded: class 1 and class 2 each have exactly one material
        class1 = repo.find_by_class(1)
        class2 = repo.find_by_class(2)
        assert len(class1) == 1 and "A班" in class1[0]["filename"]
        assert len(class2) == 1 and "B班" in class2[0]["filename"]

    def test_find_by_id_scoped_rejects_cross_class(self, test_db):
        from app.db.connection import get_connection
        from app.repositories.materials import MaterialsRepository

        conn = get_connection(test_db)
        repo = MaterialsRepository(conn)
        # Seeded material id=1 belongs to class 1
        assert repo.find_by_id_scoped_to_class(1, 1) is not None
        assert repo.find_by_id_scoped_to_class(1, 2) is None


class TestCrossClassRejection:
    def test_a_class_user_only_sees_a_materials(self, teacher_a, teacher_b):
        """A class user GET /materials → only A class records."""
        resp = _upload(teacher_b, b"b-content", "b_doc.txt")
        assert resp.status_code == 201

        resp = teacher_a.get("/materials")
        assert resp.status_code == 200
        materials = resp.get_json()["materials"]
        # Seeded A material + nothing from B
        assert len(materials) == 1
        assert materials[0]["class_id"] == 1

    def test_a_class_user_cannot_get_b_class_material_detail(self, teacher_a, teacher_b):
        """A class user GET /materials/{B's id} → 404, same as non-existent."""
        resp = _upload(teacher_b, b"secret", "secret.txt")
        b_material_id = resp.get_json()["id"]

        cross = teacher_a.get(f"/materials/{b_material_id}")
        missing = teacher_a.get("/materials/99999")
        assert cross.status_code == 404
        assert missing.status_code == 404
        assert cross.get_json() == missing.get_json()

    def test_teacher_cross_class_also_rejected(self, teacher_a, teacher_b):
        resp = _upload(teacher_b, b"private", "private.txt")
        b_id = resp.get_json()["id"]
        assert teacher_a.get(f"/materials/{b_id}").status_code == 404


class TestDirectURLBypass:
    def test_constructed_id_still_filtered(self, teacher_b, teacher_a):
        """Direct URL construction cannot bypass session-scoped class filter."""
        resp = _upload(teacher_b, b"x", "x.txt")
        target_id = resp.get_json()["id"]
        assert teacher_a.get(f"/materials/{target_id}").status_code == 404
