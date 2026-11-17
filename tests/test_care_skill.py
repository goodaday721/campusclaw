"""Lesson 11 拓展：关怀式对话技能.

The care skill is seeded enabled and bound to the default agent, but the chat
pipeline injects it ONLY when the student's message signals frustration. A
distress turn with zero retrieval hits still calls the model (otherwise the
fixed "not found" line would answer at the worst possible moment).
"""
import io

from app.services import chat
from app.services.answer import NO_MATCH_MESSAGE
from tests.conftest import execute, query_one

DISTRESS = "这道题我完全不会，好难，有点想放弃了"
NORMAL = "什么是方程"

DISTRESS_MATERIAL = "遇到不会的题不要放弃：先读题，再写出已知条件，一步一步来。"
NORMAL_MATERIAL = "什么是方程：含有未知数的等式叫方程。"


def _upload(client, filename, content):
    return client.post(
        "/materials",
        data={"file": (io.BytesIO(content.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )


def _agent_id(client):
    agents = client.get("/api/agents").get_json()["agents"]
    assert agents, "seeded agent missing"
    return agents[0]["id"]


def _ask(client, content):
    cid = client.post(
        "/api/conversations", json={"agent_id": _agent_id(client)}
    ).get_json()["conversation"]["id"]
    resp = client.post(f"/api/conversations/{cid}/messages", json={"content": content})
    assert resp.status_code == 200
    return cid, resp.get_data(as_text=True)


class TestCareSkillSeeded:
    def test_seeded_and_bound_in_both_classes(self, test_db):
        for class_id in (1, 2):
            row = query_one(
                test_db,
                "SELECT id, enabled FROM skills WHERE class_id = %s AND name = %s",
                (class_id, "关怀式对话"),
            )
            assert row is not None, f"class {class_id} missing 关怀式对话"
            assert row["enabled"] == 1
            bound = query_one(
                test_db,
                "SELECT count(*) AS n FROM agent_skills WHERE skill_id = %s",
                (row["id"],),
            )
            assert bound["n"] >= 1

    def test_needs_care_detector(self):
        assert chat.needs_care("我不会做这道题")
        assert chat.needs_care("压力好大，想放弃")
        assert not chat.needs_care("解一元一次方程的步骤是什么")
        assert not chat.needs_care("")


class TestCareInjection:
    def test_distress_injects_care(self, teacher_a, student_a, chat_stream_spy, test_db):
        assert _upload(teacher_a, "care.txt", DISTRESS_MATERIAL).status_code == 201
        cid, body = _ask(student_a, DISTRESS)
        assert body  # SSE body streamed
        system = chat_stream_spy[0][0]["content"]
        assert "【技能：关怀式对话】" in system
        # 其余内置技能依然注入
        assert "【技能：方程解题引导】" in system
        assert "【技能：错题讲解】" in system

        row = query_one(
            test_db,
            "SELECT skill_name FROM messages WHERE conversation_id = %s AND role = 'assistant'",
            (cid,),
        )
        assert "关怀式对话" in row["skill_name"]

    def test_normal_message_excludes_care(self, teacher_a, student_a, chat_stream_spy, test_db):
        assert _upload(teacher_a, "normal.txt", NORMAL_MATERIAL).status_code == 201
        cid, _ = _ask(student_a, NORMAL)
        system = chat_stream_spy[0][0]["content"]
        assert "【技能：关怀式对话】" not in system
        assert "【技能：方程解题引导】" in system

        row = query_one(
            test_db,
            "SELECT skill_name FROM messages WHERE conversation_id = %s AND role = 'assistant'",
            (cid,),
        )
        assert "关怀式对话" not in (row["skill_name"] or "")

    def test_disabled_care_is_not_injected(self, teacher_a, student_a, chat_stream_spy, test_db):
        assert _upload(teacher_a, "care2.txt", DISTRESS_MATERIAL).status_code == 201
        execute(
            test_db,
            "UPDATE skills SET enabled = 0 WHERE class_id = 1 AND name = '关怀式对话'",
        )
        _ask(student_a, DISTRESS)
        system = chat_stream_spy[0][0]["content"]
        assert "【技能：关怀式对话】" not in system


class TestCareZeroHit:
    def test_distress_without_materials_calls_model(self, student_a, chat_stream_spy):
        _, body = _ask(student_a, DISTRESS)
        assert len(chat_stream_spy) == 1, "关怀轮次必须调用模型"
        assert NO_MATCH_MESSAGE not in body
        assert "引导式测试回答" in body

    def test_normal_without_materials_keeps_fixed_message(self, student_a, chat_stream_spy):
        _, body = _ask(student_a, NORMAL)
        assert chat_stream_spy == [], "普通零命中不调用模型"
        assert NO_MATCH_MESSAGE in body
