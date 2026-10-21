"""POST /api/skills — setup for the z-full-chain case (runs before it).

Creates the teacher-side chain in one go: a skill whose source references
``unit_convert@campus-tools`` (the case request itself), then an agent bound to
that skill and a student conversation on it (via follow-up requests in
check()). Lives under ``y-`` so the directory sort places it before
``z-full-chain``, which needs ctx["mcp_conversation_id"].
"""
import time

import requests

SUFFIX = int(time.time())
SOURCE = (
    f"名称：apitest换算技能{SUFFIX}\n"
    "适用条件：学生提出涉及单位换算的问题时\n"
    "工具：unit_convert@campus-tools\n"
    "启用：是\n"
    "\n"
    "遇到单位换算先调用换算工具拿数据，再引导学生理解进率，不直接给答案。"
)


def skip_if(ctx):
    return None if ctx.get("mcp_server_id") else "no seed server listed by the GET case"


def check(resp, ctx):
    assert resp.status_code == 201, f"status {resp.status_code}: {resp.text[:200]}"
    skill = resp.json()["skill"]
    assert skill["enabled"] is True
    ctx["mcp_skill_id"] = skill["id"]

    def _post(path, payload, role):
        return requests.post(
            f"{ctx['base_url']}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {ctx['tokens'][role]}"},
            timeout=60,
        )

    agent_resp = _post(
        "/api/agents",
        {"name": f"apitest换算助手{SUFFIX}", "skill_ids": [skill["id"]]},
        "teacher",
    )
    assert agent_resp.status_code == 201, f"agent create: {agent_resp.text[:200]}"
    agent_id = agent_resp.json()["agent"]["id"]

    conv_resp = _post("/api/conversations", {"agent_id": agent_id}, "student")
    assert conv_resp.status_code == 201, f"conversation create: {conv_resp.text[:200]}"
    ctx["mcp_conversation_id"] = conv_resp.json()["conversation"]["id"]


CASE = {
    "name": "全链路前置：教师建引用工具的技能并绑定智能体，学生开好会话",
    "method": "POST",
    "path": "/api/skills",
    "role": "teacher",
    "body": {"source": SOURCE},
    "skip_if": skip_if,
    "check": check,
}
