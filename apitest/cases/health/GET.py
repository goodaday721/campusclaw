"""GET /health — anonymous liveness probe."""
from helpers import db_query_one


def check(resp, ctx):
    assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data.get("status") == "ok", f"unexpected body: {data}"
    # DB consistency: the seeded classes exist behind the service.
    row = db_query_one("SELECT COUNT(*) AS n FROM classes")
    assert row and row["n"] >= 1, "no classes in database"


CASE = {
    "name": "健康检查（匿名）返回 ok",
    "method": "GET",
    "path": "/health",
    "role": None,
    "check": check,
}
