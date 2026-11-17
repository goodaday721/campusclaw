"""Lesson 11 拓展：技能上传（POST /api/skills/import）.

Covers normal (.md / .json), failure (bad extension / oversize / non-UTF8 /
bad JSON / duplicate / unknown tool / student 403) and boundary (imported
skill starts disabled, cross-class names are independent, enabling afterwards).
"""
import io
import json

from tests.conftest import query_one


def _md_source(name="导入技能A", tool=None, body="这是一段导入的引导指令正文。"):
    lines = [f"名称：{name}", "适用条件：单元测试", "资料：数学"]
    if tool:
        lines.append(f"工具：{tool}")
    lines.append("启用：是")
    return ("\n".join(lines) + "\n\n" + body).encode("utf-8")


def _upload(client, filename, content):
    return client.post(
        "/api/skills/import",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def _names(client):
    return [s["name"] for s in client.get("/api/skills").get_json()["skills"]]


class TestImportNormal:
    def test_import_md_creates_disabled_skill(self, teacher_a, test_db):
        resp = _upload(teacher_a, "a.md", _md_source())
        assert resp.status_code == 201
        skill = resp.get_json()["skill"]
        assert skill["name"] == "导入技能A"
        assert skill["enabled"] is False
        assert "启用：否" in skill["source"]
        assert "这是一段导入的引导指令正文。" in skill["source"]

        row = query_one(
            test_db,
            "SELECT enabled, source FROM skills WHERE class_id = 1 AND name = %s",
            ("导入技能A",),
        )
        assert row["enabled"] == 0
        assert "启用：否" in row["source"]

    def test_import_json_flat_fields(self, teacher_a):
        payload = {
            "name": "JSON技能",
            "trigger": "单元测试",
            "subject": "数学",
            "description": "来自 JSON 的引导正文。",
            "tools": [],
        }
        resp = _upload(
            teacher_a, "b.json", json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        assert resp.status_code == 201
        skill = resp.get_json()["skill"]
        assert skill["name"] == "JSON技能"
        assert skill["description"] == "来自 JSON 的引导正文。"
        assert skill["enabled"] is False

    def test_import_json_with_source(self, teacher_a):
        payload = {"source": _md_source(name="JSON源码技能").decode("utf-8")}
        resp = _upload(
            teacher_a, "c.json", json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        assert resp.status_code == 201
        assert resp.get_json()["skill"]["name"] == "JSON源码技能"

    def test_import_utf8_bom_is_accepted(self, teacher_a):
        # Windows 记事本默认写 UTF-8 BOM，不能因此报「缺少名称行」
        assert _upload(teacher_a, "bom.md", b"\xef\xbb\xbf" + _md_source(name="BOM技能")).status_code == 201

    def test_import_is_audited(self, teacher_a, test_db):
        _upload(teacher_a, "audited.md", _md_source(name="审计技能"))
        row = query_one(
            test_db,
            "SELECT action, target_type, skill_name, detail FROM audit_logs "
            "WHERE target_type = 'skill' ORDER BY id DESC LIMIT 1",
        )
        assert row["action"] == "create"
        assert row["skill_name"] == "审计技能"
        detail = json.loads(row["detail"])
        assert detail["import"] is True
        assert detail["filename"] == "audited.md"


class TestImportFailures:
    def test_bad_extension_415(self, teacher_a):
        assert _upload(teacher_a, "evil.py", b"print(1)").status_code == 415
        assert _upload(teacher_a, "noext", b"data").status_code == 415

    def test_oversize_413(self, teacher_a):
        big = _md_source(body="x" * (65 * 1024))
        assert _upload(teacher_a, "big.md", big).status_code == 413

    def test_non_utf8_400(self, teacher_a):
        assert _upload(teacher_a, "gbk.md", "名称：中文".encode("gbk")).status_code == 400

    def test_bad_json_400(self, teacher_a):
        assert _upload(teacher_a, "bad.json", b"{not json").status_code == 400
        assert _upload(teacher_a, "list.json", b"[]").status_code == 400
        missing = json.dumps({"name": "只有名字"}).encode("utf-8")
        assert _upload(teacher_a, "missing.json", missing).status_code == 400

    def test_missing_name_or_body_400(self, teacher_a):
        no_body = "名称：无正文\n\n".encode("utf-8")
        assert _upload(teacher_a, "nobody.md", no_body).status_code == 400
        no_name = "适用条件：x\n\n有正文没名字".encode("utf-8")
        assert _upload(teacher_a, "noname.md", no_name).status_code == 400

    def test_duplicate_name_409(self, teacher_a):
        assert _upload(teacher_a, "one.md", _md_source(name="重复技能")).status_code == 201
        assert _upload(teacher_a, "two.md", _md_source(name="重复技能")).status_code == 409

    def test_unknown_tool_reference_400(self, teacher_a):
        resp = _upload(teacher_a, "tool.md", _md_source(tool="no_such_tool@no_such_server"))
        assert resp.status_code == 400
        assert "no_such_server" in resp.get_json()["error"]

    def test_student_403(self, student_a):
        assert _upload(student_a, "s.md", _md_source(name="学生技能")).status_code == 403

    def test_unauthenticated_401(self, app_client):
        assert _upload(app_client, "x.md", _md_source(name="匿名技能")).status_code == 401

    def test_missing_file_400(self, teacher_a):
        resp = teacher_a.post("/api/skills/import", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400


class TestImportBoundary:
    def test_disabled_skill_hidden_from_students_then_visible(self, teacher_a, student_a):
        assert _upload(teacher_a, "p.md", _md_source(name="待启用技能")).status_code == 201
        assert "待启用技能" not in _names(student_a)

        skill_id = None
        for skill in teacher_a.get("/api/skills").get_json()["skills"]:
            if skill["name"] == "待启用技能":
                skill_id = skill["id"]
                break
        assert skill_id is not None

        enable_source = _md_source(name="待启用技能").decode("utf-8").replace(
            "启用：是", "启用：是"
        )
        put = teacher_a.put(
            f"/api/skills/{skill_id}", json={"source": enable_source}
        )
        assert put.status_code == 200
        assert put.get_json()["skill"]["enabled"] is True
        assert "待启用技能" in _names(student_a)

    def test_same_name_allowed_in_other_class(self, teacher_a, teacher_b):
        assert _upload(teacher_a, "a.md", _md_source(name="同名技能")).status_code == 201
        assert _upload(teacher_b, "b.md", _md_source(name="同名技能")).status_code == 201
