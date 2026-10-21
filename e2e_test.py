#!/usr/bin/env python
"""End-to-end test: verifies lesson-3/4 spec scenarios in order (Bearer-token auth).

Can run against docker compose up (HTTP via the web entry) or directly via
Flask test client (requires a reachable MySQL test database).
Usage:
    python e2e_test.py          # Flask test client mode
    python e2e_test.py --http   # HTTP mode via http://localhost:8080 (Nginx)
"""
import io
import json
import os
import sys
import urllib.request

# ---- Flask test client mode ----
def run_with_test_client():
    import pathlib

    ROOT = pathlib.Path(__file__).resolve().parent

    # MySQL test DB — TEST_DB_* (when set) wins over the app's DB_* values,
    # because the app user may not have rights on the freshly created test db.
    os.environ["DB_HOST"] = os.environ.get("TEST_DB_HOST", os.environ.get("DB_HOST", "127.0.0.1"))
    os.environ["DB_PORT"] = os.environ.get("TEST_DB_PORT", os.environ.get("DB_PORT", "3306"))
    os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "campusclaw_test")
    os.environ["DB_USER"] = os.environ.get("TEST_DB_USER", os.environ.get("DB_USER", "root"))
    os.environ["DB_PASSWORD"] = os.environ.get("TEST_DB_PASSWORD", os.environ.get("DB_PASSWORD", ""))
    os.environ["SESSION_TTL_HOURS"] = "24"
    os.environ.setdefault("JWT_SECRET", "e2e-jwt-secret")
    os.environ["UPLOAD_ROOT"] = str(ROOT / "uploads")
    # Lesson 4: isolated Qdrant test collection.
    os.environ["QDRANT_HOST"] = os.environ.get("TEST_QDRANT_HOST", "127.0.0.1")
    os.environ["QDRANT_COLLECTION"] = "campusclaw_chunks_e2e"

    import pymysql

    test_db_name = os.environ["DB_NAME"]
    server = pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
    )
    with server.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
        cur.execute(f"CREATE DATABASE {test_db_name} CHARACTER SET utf8mb4")
    server.close()

    from app.config import Config
    from app import create_app
    from app.db.connection import get_connection
    from app.services import model_gateway, vector_store
    from tests.conftest import BearerClient, _fake_embed_texts, query_one

    # Clean vector collection + offline deterministic fakes.
    _qcfg = Config().qdrant_config()
    try:
        vector_store._client(_qcfg).delete_collection(_qcfg["collection"])
    except Exception:
        pass
    model_gateway.embed_texts = _fake_embed_texts
    model_gateway.chat = lambda cfg, messages: "根据班级资料[1]，e2e回答。"

    config = Config()
    config.vector_threshold = 0.0
    app = create_app(config)
    app.testing = True

    db = {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ["DB_PORT"]),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": test_db_name,
    }

    results = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        results.append((name, status, detail))
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    def new_client():
        return app.test_client()

    def login_new(username: str, password: str):
        """Login on a fresh client; return (BearerClient, login response)."""
        c = new_client()
        r = c.post("/auth/login", json={"username": username, "password": password})
        return BearerClient(c, r.get_json()["token"]), r

    def upload(client, content: bytes, filename: str, **extra):
        data = {"file": (io.BytesIO(content), filename), **extra}
        return client.post("/materials", data=data, content_type="multipart/form-data")

    print("=== E2E Test (Flask test client) ===")

    # 1. Health check
    c = new_client()
    r = c.get("/health")
    check("health 200", r.status_code == 200, str(r.get_json()))

    # 2. Logins — each user gets their own Bearer client (JWT from response body)
    ta, r = login_new("teacher_a", "teacher_a_pass")
    check("teacher_a login", r.status_code == 200, f"status={r.status_code}")
    check("login returns JWT token", len((r.get_json() or {}).get("token", "").split(".")) == 3)
    check("login sets no cookie", "Set-Cookie" not in r.headers)

    tb, _ = login_new("teacher_b", "teacher_b_pass")
    sa, _ = login_new("student_a", "student_a_pass")

    # 3. Re-login issues a distinct token (multi-device: both stay valid)
    _, r2 = login_new("teacher_a", "teacher_a_pass")
    check("re-login issues distinct token", r2.get_json()["token"] != ta.token)

    # 4. Teacher upload → two tables consistent
    r = upload(ta, b"lesson content", "lesson.txt")
    check("teacher upload 201", r.status_code == 201, f"status={r.status_code}")
    uploaded_id = r.get_json()["id"]
    check("upload class_id from session", r.get_json()["class_id"] == 1)
    entry = query_one(
        db,
        "SELECT class_id, content FROM knowledge_entries WHERE material_id = %s",
        (uploaded_id,),
    )
    check(
        "knowledge_entries row consistent",
        entry is not None and entry["class_id"] == 1 and entry["content"] == "lesson content",
    )

    # 5. Lists: teacher + student see it
    r = ta.get("/materials")
    check("teacher list has upload", any(m["id"] == uploaded_id for m in r.get_json()["materials"]))
    r = sa.get("/materials")
    check("student list has upload", any(m["id"] == uploaded_id for m in r.get_json()["materials"]))

    # 6. Student upload 403
    r = upload(sa, b"hack", "hack.txt")
    check("student upload 403", r.status_code == 403, f"status={r.status_code}")

    # 7. Cross-class detail + download: same-shape 404
    r = upload(tb, b"b-only", "secret.txt")
    b_id = r.get_json()["id"]
    r_detail = ta.get(f"/materials/{b_id}")
    r_dl = ta.get(f"/materials/{b_id}/download")
    r_missing = ta.get("/materials/99999/download")
    check("cross-class detail 404", r_detail.status_code == 404)
    check(
        "cross-class download same-shape 404",
        r_dl.status_code == 404 and r_dl.get_json() == r_missing.get_json(),
    )

    # 8. Classmate download returns uploaded content
    r = sa.get(f"/materials/{uploaded_id}/download")
    check("classmate download content", r.status_code == 200 and r.data == b"lesson content")

    # 9. Logout invalidates immediately (server-side revocation)
    sa_token = sa.token
    r = sa.post("/auth/logout")
    check("logout 200", r.status_code == 200, f"status={r.status_code}")
    stale = BearerClient(new_client(), sa_token)
    r = stale.get("/materials")
    check("token dead after logout", r.status_code == 401, f"status={r.status_code}")

    # 10. Lesson-4 retrieval: keyword / vector / hybrid + sourcing
    r = ta.post("/search", json={"query": "lesson", "mode": "keyword"})
    d = r.get_json()
    check("keyword search 200", r.status_code == 200, f"status={r.status_code}")
    check(
        "keyword finds uploaded material",
        r.status_code == 200 and any(h["materialId"] == uploaded_id for h in d["hits"]),
    )
    hit = d["hits"][0] if d.get("hits") else {}
    check(
        "hit carries traceable source",
        {"materialTitle", "chunkIndex", "charStart", "charEnd", "excerpt",
         "materialUrl"} <= set(hit.keys()),
    )

    r = ta.post("/search", json={"query": "lesson content", "mode": "vector"})
    check("vector search 200", r.status_code == 200, f"status={r.status_code}")
    check(
        "vector finds uploaded material",
        r.status_code == 200
        and any(h["materialId"] == uploaded_id for h in r.get_json()["hits"]),
    )

    r = ta.post("/search", json={"query": "lesson"})
    check("hybrid default mode 200", r.status_code == 200 and r.get_json()["mode"] == "hybrid")

    r = ta.post("/search", json={"query": "   ", "mode": "keyword"})
    check("empty query 400", r.status_code == 400, f"status={r.status_code}")

    # Cross-class search returns 200 + empty (not 403/404)
    # Fixture text uses rare CJK chars: they match the B-class upload (so a
    # scoping bug WOULD surface) but cannot bigram-collide with any A-class
    # material content (which may contain English words like "sessions").
    r = upload(tb, "鵨鶄鶅鶆鶇鶈鶉鶊鶋".encode(), "brare.txt")
    r = ta.post("/search", json={"query": "鵨鶄鶅鶆鶇鶈鶉鶊鶋", "mode": "keyword"})
    check(
        "cross-class search 200 empty",
        r.status_code == 200 and r.get_json()["hits"] == [],
    )

    # Ask: grounded answer with citations
    r = ta.post("/ask", json={"question": "lesson content"})
    d = r.get_json()
    check("ask grounded 200", r.status_code == 200 and bool(d.get("citations")))
    config.vector_threshold = 0.99  # exclude fake-embedding hash-collision noise
    # Rare-only bigrams absent from every uploaded/seeded chunk (ASCII bigrams
    # like "co"/"le" would otherwise ngram-match "lesson content").
    r = ta.post("/ask", json={"question": "鴗鴘鶙鶣鶤鶥鶦鶧"})
    check(
        "ask no-evidence fixed message",
        r.status_code == 200
        and r.get_json()["answer"] == "资料中未找到相关内容"
        and r.get_json()["citations"] == [],
    )
    config.vector_threshold = 0.0

    # Reindex: teacher 200, student 403 (fresh student login after logout)
    r = ta.post(f"/materials/{uploaded_id}/reindex", json={"strategy": "hierarchy"})
    check("teacher reindex 200", r.status_code == 200, f"status={r.status_code}")
    sa, _ = login_new("student_a", "student_a_pass")
    r = sa.post(f"/materials/{uploaded_id}/reindex", json={"strategy": "auto"})
    check("student reindex 403", r.status_code == 403, f"status={r.status_code}")

    # 10.5 Lesson-5 assistant: teacher config -> student streaming chat (fake gateway)
    print("  --- Lesson 5: assistant streaming chat ---")
    model_gateway.chat_stream = lambda cfg, messages: iter(
        ["根据班级资料", "[1]，e2e流式引导回答。"]
    )
    sb, _ = login_new("student_b", "student_b_pass")

    def parse_sse_text(text: str):
        frames = []
        for block in text.split("\n\n"):
            ev = data = None
            for line in block.splitlines():
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
            if ev:
                try:
                    frames.append((ev, json.loads(data) if data else None))
                except ValueError:
                    frames.append((ev, data))
        return frames

    r = ta.put("/api/prompt", json={"body": "A班e2e提示词：只依据本班资料引导，不给答案。"})
    check("teacher prompt PUT 200", r.status_code == 200, f"status={r.status_code}")
    r = ta.get("/api/prompt")
    check("prompt PUT persisted", r.status_code == 200
          and r.get_json()["body"] == "A班e2e提示词：只依据本班资料引导，不给答案。")
    r = sa.put("/api/prompt", json={"body": "学生篡改"})
    check("student prompt PUT 403", r.status_code == 403, f"status={r.status_code}")

    skill_source = (
        "名称：e2e引导技能\n适用条件：e2e\n工具：knowledge_search\n"
        "资料：班级材料\n启用：是\n\n引导正文，不给最终答案。"
    )
    r = ta.post("/api/skills", json={"source": skill_source})
    check("teacher skill create 201", r.status_code == 201, f"status={r.status_code}")
    skill_id = r.get_json()["skill"]["id"]
    r = sa.post("/api/skills", json={"source": skill_source})
    check("student skill create 403", r.status_code == 403, f"status={r.status_code}")

    r = ta.post(
        "/api/agents",
        json={"name": "e2e解题助手", "prompt": "你是e2e解题助手，只引导不给答案。",
              "skill_ids": [skill_id], "material_ids": [], "enabled": True},
    )
    check("teacher agent create 201", r.status_code == 201, f"status={r.status_code}")
    agent_id = r.get_json()["agent"]["id"]

    r = sa.post("/api/conversations", json={"agent_id": agent_id})
    check("student conversation create 201", r.status_code == 201, f"status={r.status_code}")
    cid = r.get_json()["conversation"]["id"]
    check("cross-class conversation 404",
          sb.post("/api/conversations", json={"agent_id": agent_id}).status_code == 404)
    check("cross-class conversation detail 404", sb.get(f"/api/conversations/{cid}").status_code == 404)

    r = sa.post(f"/api/conversations/{cid}/messages", json={"content": "lesson content 是什么？"})
    check("SSE message 200", r.status_code == 200, f"status={r.status_code}")
    check("SSE content type", r.content_type.startswith("text/event-stream"))
    frames = parse_sse_text(r.get_data(as_text=True))  # consume -> persists
    kinds = [name for name, _ in frames]
    check(
        "SSE frame order meta->delta*->done",
        kinds[0] == "meta" and kinds[-1] == "done" and all(k == "delta" for k in kinds[1:-1]),
        str(kinds),
    )
    meta = frames[0][1]
    check("SSE meta carries citations", bool(meta.get("citations")))
    answer = "".join(d["text"] for name, d in frames if name == "delta")
    check("streamed answer assembled", answer == "根据班级资料[1]，e2e流式引导回答。", answer)
    rows = query_one(
        db,
        "SELECT (SELECT COUNT(*) FROM messages WHERE conversation_id=%s) AS n, "
        "(SELECT role FROM messages WHERE conversation_id=%s ORDER BY id DESC LIMIT 1) AS last_role",
        (cid, cid),
    )
    check("streamed turn persisted (user+assistant)", rows["n"] == 2 and rows["last_role"] == "assistant")
    assistant_row = query_one(
        db,
        "SELECT citations, skill_name FROM messages WHERE conversation_id=%s "
        "AND role='assistant' ORDER BY id DESC LIMIT 1",
        (cid,),
    )
    check(
        "assistant row citations + skill_name",
        json.loads(assistant_row["citations"]) and assistant_row["skill_name"] == "e2e引导技能",
        str(assistant_row),
    )

    # Zero-hit: fixed message, gateway never called (threshold blocks vector noise)
    config.vector_threshold = 0.99
    before_n = query_one(db, "SELECT COUNT(*) AS n FROM messages WHERE conversation_id=%s", (cid,))["n"]
    r = sa.post(f"/api/conversations/{cid}/messages", json={"content": "鴗鴘鶙鶣鶤鶥鶧"})
    frames = parse_sse_text(r.get_data(as_text=True))
    zero_answer = "".join(d["text"] for name, d in frames if name == "delta")
    check(
        "zero-hit fixed message without model call",
        r.status_code == 200 and frames[0][1]["citations"] == []
        and zero_answer == "资料中未找到相关内容" and frames[-1][0] == "done",
    )
    after_n = query_one(db, "SELECT COUNT(*) AS n FROM messages WHERE conversation_id=%s", (cid,))["n"]
    check("zero-hit turn persisted too", after_n == before_n + 2)
    config.vector_threshold = 0.0

    check("cross-class message 404",
          sb.post(f"/api/conversations/{cid}/messages", json={"content": "hi"}).status_code == 404)

    # 10.6 Lesson-6 MCP: registry -> connect -> tool skill -> tool loop -> audit
    print("  --- Lesson 6: MCP tool integration ---")
    from app.services import mcp_client

    def _fake_mcp_init(base_url, token, config):
        return {"protocolVersion": "2024-11-05", "serverInfo": {"name": "campus-tools"}}

    def _fake_mcp_list(base_url, token, config):
        return [
            {"name": "unit_convert", "description": "单位换算工具。",
             "inputSchema": {"type": "object",
                             "properties": {"value": {"type": "number"},
                                            "from_unit": {"type": "string"},
                                            "to_unit": {"type": "string"}},
                             "required": ["value", "from_unit", "to_unit"]}},
            {"name": "formula_hint", "description": "公式提示工具。",
             "inputSchema": {"type": "object",
                             "properties": {"query": {"type": "string"}},
                             "required": ["query"]}},
        ]

    mcp_calls = []

    def _fake_mcp_call(base_url, token, tool_name, arguments, config):
        mcp_calls.append({"tool": tool_name, "arguments": arguments})
        return f"{arguments.get('value')} {arguments.get('from_unit')} = 3000 {arguments.get('to_unit')}（进率 1000）。"

    mcp_client.initialize = _fake_mcp_init
    mcp_client.list_tools = _fake_mcp_list
    mcp_client.call_tool = _fake_mcp_call

    tool_loop_calls = []

    def _fake_chat_with_tools(cfg, messages, tools):
        tool_loop_calls.append({"tools": tools, "last": messages[-1]["content"]})
        if len(tool_loop_calls) == 1:
            return {"content": None,
                    "tool_calls": [{"id": "c1", "name": "unit_convert",
                                    "arguments": {"value": 3, "from_unit": "千克", "to_unit": "克"}}]}
        return {"content": "回答完成。", "tool_calls": None}

    model_gateway.chat_with_tools = _fake_chat_with_tools

    r = sa.get("/api/mcp/servers")
    check("student mcp list 403", r.status_code == 403, f"status={r.status_code}")
    r = ta.get("/api/mcp/servers")
    check("teacher mcp list 200 (seed pre-registered)",
          r.status_code == 200 and r.get_json()["servers"]
          and r.get_json()["servers"][0]["name"] == "campus-tools", f"status={r.status_code}")
    server = r.get_json()["servers"][0]
    check("server response has hasToken only",
          server["hasToken"] is True and "token" not in json.dumps(r.get_json()))

    r = ta.post(f"/api/mcp/servers/{server['id']}/connect")
    check("mcp connect 200 + 2 tools", r.status_code == 200
          and len(r.get_json()["tools"]) == 2, f"status={r.status_code}")
    r = ta.get(f"/api/mcp/servers/{server['id']}/tools")
    check("cached tools listed", r.status_code == 200
          and {t["name"] for t in r.get_json()["tools"]} == {"unit_convert", "formula_hint"})

    def tool_skill_source():
        return ("名称：e2e工具技能\n适用条件：单位换算\n"
                "工具：knowledge_search, unit_convert@campus-tools\n"
                "资料：班级材料\n启用：是\n\n先换算再引导，不给最终答案。")

    r = ta.post("/api/skills", json={"source": tool_skill_source()})
    check("tool skill create 201 (server connected)", r.status_code == 201,
          f"status={r.status_code} body={r.get_json()}")
    tool_skill_id = r.get_json()["skill"]["id"]
    r = ta.post(f"/api/mcp/servers/{server['id']}/disconnect")
    check("mcp disconnect 200", r.status_code == 200, f"status={r.status_code}")
    check("cache cleared on disconnect",
          ta.get(f"/api/mcp/servers/{server['id']}/tools").get_json()["tools"] == [])
    r = ta.post("/api/skills", json={"source": tool_skill_source()})
    check("tool skill create 400 (disconnected)", r.status_code == 400,
          f"status={r.status_code}")
    for bad in ("Formula_Hint@campus-tools", "formula-hint@campus-tools",
                "unit_convert@no-such"):
        r = ta.post("/api/skills", json={
            "source": tool_skill_source().replace("unit_convert@campus-tools", bad)})
        check(f"bad reference rejected: {bad}", r.status_code == 400, f"status={r.status_code}")

    r = ta.post(f"/api/mcp/servers/{server['id']}/connect")
    check("mcp reconnect 200", r.status_code == 200, f"status={r.status_code}")
    r = ta.post(
        "/api/agents",
        json={"name": "e2e工具智能体", "prompt": "", "skill_ids": [tool_skill_id],
              "material_ids": [], "enabled": True},
    )
    check("tool agent create 201", r.status_code == 201, f"status={r.status_code}")
    tool_agent_id = r.get_json()["agent"]["id"]
    r = sa.post("/api/conversations", json={"agent_id": tool_agent_id})
    tool_cid = r.get_json()["conversation"]["id"]

    r = sa.post(f"/api/conversations/{tool_cid}/messages",
                json={"content": "3千克等于多少克？需要单位换算。lesson content"})
    frames = parse_sse_text(r.get_data(as_text=True))
    kinds = [name for name, _ in frames]
    check("tool SSE frame order meta->delta*->done",
          kinds[0] == "meta" and kinds[-1] == "done", str(kinds))
    tmeta = frames[0][1]
    check("meta.tool_calls ok with ref/round",
          tmeta.get("tool_calls") and tmeta["tool_calls"][0]["ref"] == "unit_convert@campus-tools"
          and tmeta["tool_calls"][0]["status"] == "ok"
          and tmeta["tool_calls"][0]["round"] == 1, str(tmeta.get("tool_calls")))
    check("tool executed once with model-filled args",
          len(mcp_calls) == 1 and mcp_calls[0]["arguments"]["value"] == 3,
          str(mcp_calls))
    check("tool result entered user message as data",
          "[工具 unit_convert@campus-tools 第1轮返回的数据]" in tool_loop_calls[1]["last"])
    log_row = query_one(
        db, "SELECT * FROM mcp_call_logs WHERE conversation_id=%s", (tool_cid,))
    check("audit row ok with user/conversation/round",
          log_row and log_row["status"] == "ok" and log_row["round_no"] == 1
          and log_row["user_id"] and log_row["conversation_id"])
    r = ta.get("/api/mcp/call-logs")
    check("teacher audit endpoint shows the call",
          r.status_code == 200
          and any(c["ref"] == "unit_convert@campus-tools" and c["status"] == "ok"
                  for c in r.get_json()["calls"]))

    # Disconnect then ask again: the call is denied, chat continues.
    r = ta.post(f"/api/mcp/servers/{server['id']}/disconnect")
    check("disconnect for denial", r.status_code == 200)
    r = sa.post(f"/api/conversations/{tool_cid}/messages",
                json={"content": "5千克等于多少克？需要单位换算。lesson content"})
    frames = parse_sse_text(r.get_data(as_text=True))
    check("denied call not silently ok",
          frames[0][1].get("tool_calls")
          and frames[0][1]["tool_calls"][0]["status"] == "denied"
          and frames[-1][0] == "done")
    denied_row = query_one(
        db, "SELECT status FROM mcp_call_logs WHERE conversation_id=%s "
            "ORDER BY id DESC LIMIT 1", (tool_cid,))
    check("denied audit row recorded", denied_row and denied_row["status"] == "denied")

    # 11. Repeated startup no duplicate seed
    counts_before = {
        t: query_one(db, f"SELECT count(*) AS n FROM {t}")["n"]
        for t in ("users", "materials", "knowledge_entries")
    }
    from app import _init_db

    _init_db(db)
    counts_after = {
        t: query_one(db, f"SELECT count(*) AS n FROM {t}")["n"]
        for t in ("users", "materials", "knowledge_entries")
    }
    check("seed idempotent", counts_before == counts_after,
          f"before={counts_before} after={counts_after}")

    # Summary
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


# ---- HTTP mode ----
def run_http(base_url="http://localhost:8080"):
    results = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        results.append((name, status, detail))
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    def make_session():
        """One opener per user; the Bearer token is attached after login."""
        opener = urllib.request.build_opener()
        opener.addheaders = []
        return opener

    def login_http(opener, username: str, password: str):
        s, d = req(opener, "POST", "/auth/login", {"username": username, "password": password})
        if s == 200 and isinstance(d, dict) and d.get("token"):
            opener.addheaders = [("Authorization", f"Bearer {d['token']}")]
        return s, d

    def req(opener, method, path, data=None, raw=None, headers=None):
        h = dict(headers or {})
        body = None
        if raw is not None:
            boundary = "----e2eboundary1234"
            fname = data["file"][1]
            content = data["file"][0].read()
            parts = []
            for k, v in data.items():
                if k == "file":
                    continue
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n"
            )
            parts.append(f"--{boundary}--\r\n".encode())
            body = b"".join(parts)
            h["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif data is not None:
            body = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(f"{base_url}{path}", data=body, headers=h, method=method)
        try:
            resp = opener.open(r)
            payload = resp.read()
            try:
                return resp.status, json.loads(payload)
            except Exception:
                return resp.status, payload
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                return e.code, json.loads(payload)
            except Exception:
                return e.code, payload

    print(f"=== E2E Test (HTTP via {base_url}) ===")

    # 1. Health
    anon = make_session()
    s, _ = req(anon, "GET", "/health")
    check("health 200", s == 200, f"status={s}")

    # 2. Logins — token from response body, attached as Authorization header
    ta, tb, sa = make_session(), make_session(), make_session()
    s, d = login_http(ta, "teacher_a", "teacher_a_pass")
    check("teacher_a login", s == 200, f"status={s}")
    check("login returns JWT token", isinstance(d, dict) and len(d.get("token", "").split(".")) == 3)
    login_http(tb, "teacher_b", "teacher_b_pass")
    login_http(sa, "student_a", "student_a_pass")

    # 3. Upload (teacher) → 201
    s, d = req(ta, "POST", "/materials", data={"file": (io.BytesIO(b"lesson content"), "lesson.txt")}, raw=True)
    check("teacher upload 201", s == 201, f"status={s}")
    uploaded_id = d.get("id") if isinstance(d, dict) else None

    # 4. Student sees it in list
    s, d = req(sa, "GET", "/materials")
    check("student list has upload", s == 200 and any(m["id"] == uploaded_id for m in d.get("materials", [])))

    # 5. Student upload → 403
    s, _ = req(sa, "POST", "/materials", data={"file": (io.BytesIO(b"hack"), "hack.txt")}, raw=True)
    check("student upload 403", s == 403, f"status={s}")

    # 6. Download (classmate)
    s, body = req(sa, "GET", f"/materials/{uploaded_id}/download")
    check("classmate download content", s == 200 and body == b"lesson content")

    # 7. Lesson-4 keyword retrieval (no gateway dependency)
    s, d = req(ta, "POST", "/search", {"query": "lesson", "mode": "keyword"})
    check("keyword search 200", s == 200, f"status={s}")
    check(
        "keyword finds uploaded material",
        s == 200 and any(h.get("materialId") == uploaded_id for h in d.get("hits", []))
        if isinstance(d, dict) else False,
    )
    s, d = req(ta, "POST", "/search", {"query": "   ", "mode": "keyword"})
    check("empty query 400", s == 400, f"status={s}")

    # Cross-class search: 200 + empty hits (rare CJK fixture, see note above)
    req(tb, "POST", "/materials",
        data={"file": (io.BytesIO("鵨鶄鶅鶆鶇鶈鶉鶊鶋".encode()), "brare.txt")}, raw=True)
    s, d = req(ta, "POST", "/search", {"query": "鵨鶄鶅鶆鶇鶈鶉鶊鶋", "mode": "keyword"})
    check(
        "cross-class search 200 empty",
        s == 200 and isinstance(d, dict) and d.get("hits") == [],
    )

    # Vector search / ask depend on the gateway key: 200 when configured,
    # 503 when not — both are correct deployments, keyword stays authoritative.
    s, _ = req(ta, "POST", "/search", {"query": "lesson", "mode": "vector"})
    check("vector search 200 or 503(gateway unconfigured)", s in (200, 503), f"status={s}")
    s, d = req(ta, "POST", "/ask", {"question": "lesson"})
    check("ask 200 or 503(gateway unconfigured)", s in (200, 503), f"status={s}")
    if s == 200 and isinstance(d, dict):
        check("ask response shape", "answer" in d and "citations" in d)

    # 8. Lesson-5 assistant over real HTTP (SSE/gateway items accept 503 when
    #    the gateway key is unconfigured; config/isolation checks always run).
    sb = make_session()
    login_http(sb, "student_b", "student_b_pass")
    s, d = req(ta, "GET", "/api/prompt")
    check("prompt GET 200", s == 200 and isinstance(d, dict) and "body" in d, f"status={s}")
    s, d = req(ta, "PUT", "/api/prompt", {"body": (d or {}).get("body") or "默认提示词"})
    check("teacher prompt PUT 200", s == 200, f"status={s}")
    s, _ = req(sa, "PUT", "/api/prompt", {"body": "学生篡改"})
    check("student prompt PUT 403", s == 403, f"status={s}")

    skill_source = (
        "名称：e2e引导技能\n适用条件：e2e\n工具：knowledge_search\n"
        "资料：班级材料\n启用：是\n\n引导正文，不给最终答案。"
    )
    s, d = req(ta, "POST", "/api/skills", {"source": skill_source})
    check("teacher skill create 201", s == 201, f"status={s}")
    s, d = req(sa, "GET", "/api/skills")
    check(
        "student skills list only enabled",
        s == 200 and isinstance(d, dict)
        and all(skill.get("enabled") for skill in d.get("skills", [])),
    )
    s, d = req(sa, "GET", "/api/agents")
    agent_id = d["agents"][0]["id"] if s == 200 and isinstance(d, dict) and d.get("agents") else None
    check("student agents list has enabled agent", agent_id is not None)

    s, d = req(sa, "POST", "/api/conversations", {"agent_id": agent_id})
    check("conversation create 201", s == 201, f"status={s}")
    cid = d.get("conversation", {}).get("id") if isinstance(d, dict) else None
    if cid:
        s, _ = req(sb, "GET", f"/api/conversations/{cid}")
        check("cross-class conversation 404", s == 404, f"status={s}")
        s, body = req(sa, "POST", f"/api/conversations/{cid}/messages", {"content": "lesson"})
        if s == 200:
            text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
            check(
                "SSE frames meta->delta->done",
                "event: meta" in text and "event: delta" in text and "event: done" in text,
            )
        else:
            check("SSE 503(gateway unconfigured) accepted", s == 503, f"status={s}")

    # Summary
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_http() if "--http" in sys.argv else run_with_test_client())
