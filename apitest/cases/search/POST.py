"""POST /search — keyword retrieval over the class knowledge base."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    hits = data["hits"]
    assert data["mode"] == "keyword"
    assert len(hits) >= 1, "expected hits from the seeded A-class material"
    hit = hits[0]
    for field in ("chunkId", "materialId", "materialTitle", "excerpt"):
        assert field in hit, f"missing citation field {field}"
    # DB consistency: the hit's chunk row exists, ready, in class 1.
    row = db_query_one(
        "SELECT class_id, index_status FROM knowledge_chunks WHERE id = %s",
        (hit["chunkId"],),
    )
    assert row, "hit chunkId not found in knowledge_chunks"
    assert row["class_id"] == 1 and row["index_status"] == "ready"


CASE = {
    "name": "关键字检索命中班级资料切片",
    "method": "POST",
    "path": "/search",
    "role": "student",
    "body": {"query": "服务端会话", "mode": "keyword"},
    "check": check,
}
