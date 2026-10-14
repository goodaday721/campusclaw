"""Lesson-5 assistant tests: prompt / skills / agents / conversations + SSE chat."""
import io
import json

import pytest

from app.services import skill_source
from app.services.skill_source import SkillSourceError
from tests.conftest import query_all, query_one

RARE_TOKEN = "鸙鹦特殊词汇检索用例鹴鸂"
RARE_CONTENT = f"# 特殊章节\n{RARE_TOKEN}——这是只属于本班材料的罕见内容，用于检索验证。" * 3

SKILL_SOURCE_OK = (
    "名称：几何引导\n"
    "适用条件：平面几何\n"
    "工具：knowledge_search\n"
    "资料：数学\n"
    "启用：是\n"
    "\n"
    "先让学生画出图形并标注已知条件，逐步提示辅助线做法。"
)


def _upload(client, filename: str, content: str):
    return client.post(
        "/materials",
        data={"file": (io.BytesIO(content.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into [(event, data_dict), ...]."""
    events = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        name = ""
        data = {}
        for line in frame.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        events.append((name, data))
    return events


# ---------------- skill_source unit tests ----------------

class TestSkillSource:
    def test_parse_full_sample(self):
        fields = skill_source.parse(SKILL_SOURCE_OK)
        assert fields["name"] == "几何引导"
        assert fields["trigger"] == "平面几何"
        assert fields["tools"] == ["knowledge_search"]
        assert fields["subject"] == "数学"
        assert fields["enabled"] is True
        assert fields["description"].startswith("先让学生画出图形")

    def test_half_width_colon_and_multi_tools(self):
        fields = skill_source.parse("名称: X\n工具: a, b；c\n\n正文")
        assert fields["name"] == "X"
        assert fields["tools"] == ["a", "b", "c"]

    def test_disabled(self):
        fields = skill_source.parse("名称：X\n启用：否\n\n正文")
        assert fields["enabled"] is False

    def test_missing_name(self):
        with pytest.raises(SkillSourceError):
            skill_source.parse("适用条件：x\n\n正文")

    def test_missing_body(self):
        with pytest.raises(SkillSourceError):
            skill_source.parse("名称：X\n启用：是")

    def test_empty_source(self):
        with pytest.raises(SkillSourceError):
            skill_source.parse("   ")


# ---------------- /api/prompt ----------------

class TestPromptAPI:
    def test_get_seeded_prompt(self, flask_app, student_a):
        resp = student_a.get("/api/prompt")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["classId"] == 1
        assert "解题引导老师" in data["body"]

    def test_teacher_put_then_get(self, flask_app, teacher_a):
        resp = teacher_a.put("/api/prompt", json={"body": "新提示词：只引导不给答案"})
        assert resp.status_code == 200
        assert resp.get_json()["body"].startswith("新提示词")
        row = query_one(flask_app.config["DB"], "SELECT body FROM class_prompts WHERE class_id=1")
        assert row["body"].startswith("新提示词")

    def test_student_put_forbidden(self, flask_app, student_a):
        resp = student_a.put("/api/prompt", json={"body": "学生的提示词"})
        assert resp.status_code == 403
        row = query_one(flask_app.config["DB"], "SELECT body FROM class_prompts WHERE class_id=1")
        assert "学生的提示词" not in row["body"]

    def test_put_empty_body_400(self, teacher_a):
        assert teacher_a.put("/api/prompt", json={"body": "  "}).status_code == 400

    def test_unauthenticated_401(self, app_client):
        assert app_client.get("/api/prompt").status_code == 401


# ---------------- /api/skills ----------------

class TestSkillsAPI:
    def test_teacher_create_update_delete(self, flask_app, teacher_a):
        resp = teacher_a.post("/api/skills", json={"source": SKILL_SOURCE_OK})
        assert resp.status_code == 201
        skill = resp.get_json()["skill"]
        assert skill["name"] == "几何引导"
        assert skill["tools"] == ["knowledge_search"]
        assert skill["enabled"] is True

        row = query_one(flask_app.config["DB"], "SELECT * FROM skills WHERE id=%s", (skill["id"],))
        assert row["trigger"] == "平面几何"
        assert json.loads(row["tools"]) == ["knowledge_search"]

        resp = teacher_a.put(
            f"/api/skills/{skill['id']}",
            json={"source": "名称：几何引导\n启用：否\n\n改后的正文"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["skill"]["enabled"] is False

        assert teacher_a.delete(f"/api/skills/{skill['id']}").status_code == 204
        assert query_one(flask_app.config["DB"], "SELECT * FROM skills WHERE id=%s", (skill["id"],)) is None

    def test_create_bad_source_400(self, teacher_a):
        assert teacher_a.post("/api/skills", json={"source": "名称：X"}).status_code == 400
        assert teacher_a.post("/api/skills", json={"source": "  "}).status_code == 400

    def test_student_write_forbidden(self, student_a):
        assert student_a.post("/api/skills", json={"source": SKILL_SOURCE_OK}).status_code == 403
        assert student_a.put("/api/skills/1", json={"source": SKILL_SOURCE_OK}).status_code == 403
        assert student_a.delete("/api/skills/1").status_code == 403

    def test_student_sees_enabled_only(self, teacher_a, student_a):
        resp = teacher_a.post("/api/skills", json={"source": SKILL_SOURCE_OK})
        sid_on = resp.get_json()["skill"]["id"]
        resp = teacher_a.post(
            "/api/skills", json={"source": "名称：停用技能\n启用：否\n\n不注入的正文"}
        )
        sid_off = resp.get_json()["skill"]["id"]

        teacher_names = [s["id"] for s in teacher_a.get("/api/skills").get_json()["skills"]]
        student_names = [s["id"] for s in student_a.get("/api/skills").get_json()["skills"]]
        assert sid_on in teacher_names and sid_off in teacher_names
        assert sid_on in student_names and sid_off not in student_names

    def test_cross_class_404(self, flask_app, teacher_a, teacher_b):
        sid = teacher_a.post("/api/skills", json={"source": SKILL_SOURCE_OK}).get_json()["skill"]["id"]
        assert teacher_b.put(f"/api/skills/{sid}", json={"source": SKILL_SOURCE_OK}).status_code == 404
        assert teacher_b.delete(f"/api/skills/{sid}").status_code == 404
        b_ids = [s["id"] for s in teacher_b.get("/api/skills").get_json()["skills"]]
        assert sid not in b_ids


# ---------------- /api/agents ----------------

class TestAgentsAPI:
    def _skill(self, teacher, source=SKILL_SOURCE_OK):
        return teacher.post("/api/skills", json={"source": source}).get_json()["skill"]["id"]

    def test_create_and_get(self, flask_app, teacher_a):
        sid = self._skill(teacher_a)
        resp = teacher_a.post("/api/agents", json={
            "name": "几何助手", "prompt": "专用提示词", "skill_ids": [sid],
            "material_ids": [], "enabled": True,
        })
        assert resp.status_code == 201
        agent = resp.get_json()["agent"]
        assert agent["skillIds"] == [sid]
        assert agent["enabled"] is True
        got = teacher_a.get(f"/api/agents/{agent['id']}").get_json()["agent"]
        assert got["name"] == "几何助手"

    def test_cross_class_binding_404(self, teacher_a, teacher_b):
        b_sid = self._skill(teacher_b)
        resp = teacher_a.post("/api/agents", json={
            "name": "坏绑定", "skill_ids": [b_sid], "material_ids": [],
        })
        assert resp.status_code == 404

    def test_student_visibility_and_write(self, flask_app, teacher_a, student_a):
        sid_on = self._skill(teacher_a)
        agent_on = teacher_a.post("/api/agents", json={
            "name": "启用A", "skill_ids": [sid_on], "material_ids": [],
        }).get_json()["agent"]
        agent_off = teacher_a.post("/api/agents", json={
            "name": "停用A", "skill_ids": [], "material_ids": [], "enabled": False,
        }).get_json()["agent"]

        ids = [a["id"] for a in student_a.get("/api/agents").get_json()["agents"]]
        assert agent_on["id"] in ids and agent_off["id"] not in ids
        assert student_a.get(f"/api/agents/{agent_off['id']}").status_code == 404
        assert student_a.put(f"/api/agents/{agent_on['id']}", json={
            "name": "劫持", "skill_ids": [], "material_ids": [],
        }).status_code == 403

    def test_teacher_update(self, teacher_a):
        sid = self._skill(teacher_a)
        agent = teacher_a.post("/api/agents", json={
            "name": "旧名", "skill_ids": [], "material_ids": [],
        }).get_json()["agent"]
        resp = teacher_a.put(f"/api/agents/{agent['id']}", json={
            "name": "新名", "prompt": "新的", "skill_ids": [sid],
            "material_ids": [], "enabled": False,
        })
        assert resp.status_code == 200
        updated = resp.get_json()["agent"]
        assert updated["name"] == "新名" and updated["skillIds"] == [sid]
        assert updated["enabled"] is False


# ---------------- /api/conversations + SSE ----------------

class TestConversationsAPI:
    def _agent_id(self, teacher, enabled=True):
        return teacher.post("/api/agents", json={
            "name": "会话用智能体", "skill_ids": [], "material_ids": [],
            "enabled": enabled,
        }).get_json()["agent"]["id"]

    def test_create_and_detail(self, flask_app, teacher_a, student_a):
        agent_id = self._agent_id(teacher_a)
        resp = student_a.post("/api/conversations", json={"agent_id": agent_id})
        assert resp.status_code == 201
        conv = resp.get_json()["conversation"]
        assert conv["agentId"] == agent_id

        detail = student_a.get(f"/api/conversations/{conv['id']}")
        assert detail.status_code == 200
        assert detail.get_json()["conversation"]["id"] == conv["id"]
        assert detail.get_json()["messages"] == []

    def test_create_with_disabled_agent_student_404(self, teacher_a, student_a):
        agent_id = self._agent_id(teacher_a, enabled=False)
        assert student_a.post("/api/conversations", json={"agent_id": agent_id}).status_code == 404

    def test_create_cross_class_agent_404(self, teacher_a, student_b):
        agent_id = self._agent_id(teacher_a)
        assert student_b.post("/api/conversations", json={"agent_id": agent_id}).status_code == 404

    def test_detail_not_owned_or_cross_class_404(self, teacher_a, student_a, student_b):
        agent_id = self._agent_id(teacher_a)
        cid = student_a.post("/api/conversations", json={"agent_id": agent_id}) \
            .get_json()["conversation"]["id"]
        assert student_b.get(f"/api/conversations/{cid}").status_code == 404
        assert teacher_a.get(f"/api/conversations/{cid}").status_code == 404

    def test_sse_hit_flow(self, flask_app, teacher_a, student_a, chat_stream_spy):
        assert _upload(teacher_a, "rare.txt", RARE_CONTENT).status_code == 201
        agent_id = teacher_post_agent(student_a)  # students cannot create; use seeded agent
        resp = student_a.post("/api/conversations", json={"agent_id": agent_id})
        cid = resp.get_json()["conversation"]["id"]

        resp = student_a.post(
            f"/api/conversations/{cid}/messages", json={"content": RARE_TOKEN + " 是什么？"}
        )
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")
        assert resp.headers.get("X-Accel-Buffering") == "no"

        events = _parse_sse(resp.get_data(as_text=True))
        kinds = [name for name, _ in events]
        assert kinds[0] == "meta" and kinds[-1] == "done"
        assert all(k == "delta" for k in kinds[1:-1])

        meta = events[0][1]
        assert meta["status"] == "ok"
        assert len(meta["citations"]) >= 1
        assert meta["citations"][0]["materialTitle"] == "rare.txt"
        answer = "".join(d["text"] for _, d in events if _ == "delta")
        assert answer == "根据班级资料[1]，这是引导式测试回答。"

        # model messages: system + user(sources) —— 无历史
        assert chat_stream_spy[0][0]["role"] == "system"
        assert "【技能：" in chat_stream_spy[0][0]["content"]  # 种子技能注入
        assert RARE_TOKEN in chat_stream_spy[0][-1]["content"]

        rows = query_all(
            flask_app.config["DB"],
            "SELECT role, content, citations, skill_name FROM messages "
            "WHERE conversation_id=%s ORDER BY id",
            (cid,),
        )
        assert [r["role"] for r in rows] == ["user", "assistant"]
        assert rows[1]["content"] == answer
        assert json.loads(rows[1]["citations"])[0]["materialTitle"] == "rare.txt"
        assert rows[1]["skill_name"] == "方程解题引导"

        conv = student_a.get(f"/api/conversations/{cid}").get_json()
        assert conv["conversation"]["title"].startswith(RARE_TOKEN)

    def test_sse_second_turn_carries_history(self, flask_app, teacher_a, student_a, chat_stream_spy):
        agent_id = teacher_post_agent(student_a)
        cid = student_a.post("/api/conversations", json={"agent_id": agent_id}) \
            .get_json()["conversation"]["id"]
        assert _upload(teacher_a, "rare.txt", RARE_CONTENT).status_code == 201
        # NOTE: the SSE generator only runs (and persists) when the response
        # body is consumed; the test client does not iterate it implicitly.
        first = student_a.post(
            f"/api/conversations/{cid}/messages", json={"content": RARE_TOKEN + "？"}
        )
        assert first.status_code == 200
        first.get_data(as_text=True)
        second_resp = student_a.post(
            f"/api/conversations/{cid}/messages", json={"content": RARE_TOKEN + " 再讲讲？"}
        )
        assert second_resp.status_code == 200
        second_resp.get_data(as_text=True)
        assert len(chat_stream_spy) == 2
        second = chat_stream_spy[1]
        roles = [m["role"] for m in second]
        # system + (user, assistant 历史) + user(本轮 sources)
        assert roles[0] == "system"
        assert "user" in roles[1:-1] and "assistant" in roles[1:-1]
        assert roles[-1] == "user"

    def test_sse_zero_hit_no_model_call(self, flask_app, student_a, chat_stream_spy):
        agent_id = teacher_post_agent(student_a)
        cid = student_a.post("/api/conversations", json={"agent_id": agent_id}) \
            .get_json()["conversation"]["id"]
        resp = student_a.post(
            f"/api/conversations/{cid}/messages",
            json={"content": "鴗鴘鴙毫无关系的词组问题"},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.get_data(as_text=True))
        assert events[0][1]["citations"] == []
        text = "".join(d["text"] for name, d in events if name == "delta")
        assert text == "资料中未找到相关内容"
        assert events[-1][0] == "done"
        assert len(chat_stream_spy) == 0  # 网关未被调用

        rows = query_all(
            flask_app.config["DB"],
            "SELECT role, citations FROM messages WHERE conversation_id=%s ORDER BY id",
            (cid,),
        )
        assert [r["role"] for r in rows] == ["user", "assistant"]
        assert json.loads(rows[1]["citations"]) == []

    def test_message_auth_and_validation(self, app_client, student_a):
        agent_id = teacher_post_agent(student_a)
        cid = student_a.post("/api/conversations", json={"agent_id": agent_id}) \
            .get_json()["conversation"]["id"]
        assert app_client.post(
            f"/api/conversations/{cid}/messages", json={"content": "hi"}
        ).status_code == 401
        assert student_a.post(
            f"/api/conversations/{cid}/messages", json={"content": "  "}
        ).status_code == 400

    def test_cross_class_message_404(self, teacher_a, student_b):
        agent_id = teacher_post_agent(teacher_a)
        cid = teacher_a.post("/api/conversations", json={"agent_id": agent_id}) \
            .get_json()["conversation"]["id"]
        resp = student_b.post(f"/api/conversations/{cid}/messages", json={"content": "hi"})
        assert resp.status_code == 404

    def test_agent_material_filter(self, flask_app, teacher_a, chat_stream_spy):
        assert _upload(teacher_a, "rare.txt", RARE_CONTENT).status_code == 201
        sid = teacher_a.post("/api/skills", json={"source": SKILL_SOURCE_OK}) \
            .get_json()["skill"]["id"]
        materials = teacher_a.get("/materials").get_json()["materials"]
        seeded = next(m for m in materials if "第3课阅读材料" in m["filename"])
        agent_id = teacher_a.post("/api/agents", json={
            "name": "限定材料", "skill_ids": [sid],
            "material_ids": [seeded["id"]], "enabled": True,
        }).get_json()["agent"]["id"]
        cid = teacher_a.post("/api/conversations", json={"agent_id": agent_id}) \
            .get_json()["conversation"]["id"]
        resp = teacher_a.post(
            f"/api/conversations/{cid}/messages", json={"content": RARE_TOKEN + "？"}
        )
        events = _parse_sse(resp.get_data(as_text=True))
        # rare.txt 命中检索但不在智能体限定材料内 → 0 命中话术
        assert events[0][1]["citations"] == []
        text = "".join(d["text"] for name, d in events if name == "delta")
        assert text == "资料中未找到相关内容"
        assert len(chat_stream_spy) == 0


def teacher_post_agent(client):
    """Students (and teachers) reuse the seeded per-class enabled agent."""
    agents = client.get("/api/agents").get_json()["agents"]
    assert agents, "seeded agent missing"
    return agents[0]["id"]
