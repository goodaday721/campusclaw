#!/usr/bin/env python
"""End-to-end test: verifies lesson-3 spec scenarios in order (session-based).

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
from http.cookiejar import CookieJar

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
    from tests.conftest import _fake_embed_texts, query_one

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

    def upload(client, content: bytes, filename: str, **extra):
        data = {"file": (io.BytesIO(content), filename), **extra}
        return client.post("/materials", data=data, content_type="multipart/form-data")

    print("=== E2E Test (Flask test client) ===")

    # 1. Health check
    c = new_client()
    r = c.get("/health")
    check("health 200", r.status_code == 200, str(r.get_json()))

    # 2. Logins — each user gets their own client (session cookie held by client)
    ta = new_client()
    r = ta.post("/auth/login", json={"username": "teacher_a", "password": "teacher_a_pass"})
    check("teacher_a login", r.status_code == 200, f"status={r.status_code}")
    check("login sets HttpOnly cookie", "HttpOnly" in r.headers.get("Set-Cookie", ""))
    check("login response has no token", "token" not in (r.get_json() or {}))

    tb = new_client()
    tb.post("/auth/login", json={"username": "teacher_b", "password": "teacher_b_pass"})
    sa = new_client()
    sa.post("/auth/login", json={"username": "student_a", "password": "student_a_pass"})

    # 3. Session fixation defense: re-login re-issues a new session id
    old_cookie = ta.get_cookie("session_id")
    ta.post("/auth/login", json={"username": "teacher_a", "password": "teacher_a_pass"})
    new_cookie = ta.get_cookie("session_id")
    check("re-login reissues session id", old_cookie != new_cookie)

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

    # 9. Logout invalidates immediately
    r = sa.post("/auth/logout")
    check("logout 204", r.status_code == 204, f"status={r.status_code}")
    r = sa.get("/materials")
    check("session dead after logout", r.status_code == 401, f"status={r.status_code}")

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
    r = upload(tb, b"b-only secret phrase xyz", "bsecret.txt")
    r = ta.post("/search", json={"query": "secret phrase xyz", "mode": "keyword"})
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

    # Reindex: teacher 200, student 403
    r = ta.post(f"/materials/{uploaded_id}/reindex", json={"strategy": "hierarchy"})
    check("teacher reindex 200", r.status_code == 200, f"status={r.status_code}")
    r = sa.post("/auth/login", json={"username": "student_a", "password": "student_a_pass"})
    r = sa.post(f"/materials/{uploaded_id}/reindex", json={"strategy": "auto"})
    check("student reindex 403", r.status_code == 403, f"status={r.status_code}")

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
        """One cookie jar per user; HttpOnly cookies are managed by the jar."""
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        opener.addheaders = []
        return opener

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

    # 2. Logins
    ta, tb, sa = make_session(), make_session(), make_session()
    s, d = req(ta, "POST", "/auth/login", {"username": "teacher_a", "password": "teacher_a_pass"})
    check("teacher_a login", s == 200, f"status={s}")
    req(tb, "POST", "/auth/login", {"username": "teacher_b", "password": "teacher_b_pass"})
    req(sa, "POST", "/auth/login", {"username": "student_a", "password": "student_a_pass"})

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

    # Cross-class search: 200 + empty hits
    req(tb, "POST", "/materials",
        data={"file": (io.BytesIO(b"b-only secret phrase xyz"), "bsecret.txt")}, raw=True)
    s, d = req(ta, "POST", "/search", {"query": "secret phrase xyz", "mode": "keyword"})
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

    # Summary
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_http() if "--http" in sys.argv else run_with_test_client())
