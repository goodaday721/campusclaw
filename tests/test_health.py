"""Tests for app-runtime: GET /health (liveness only, no DB probing)."""
from app import create_app
from app.config import Config

from tests.conftest import query_one


class TestHealth:
    def test_health_success(self, app_client):
        """GET /health → 200 {"status":"ok"}, no sensitive data."""
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        # Must not leak sensitive data
        assert "password" not in str(data).lower()
        assert "secret" not in str(data).lower()

    def test_health_ignores_db_failure(self, app_client, monkeypatch):
        """DB outage must NOT change the health verdict (liveness only)."""
        import app.db.connection as db_conn

        def boom(*args, **kwargs):
            raise RuntimeError("simulated DB outage")

        monkeypatch.setattr(db_conn, "get_connection", boom)
        resp = app_client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestSeedIdempotent:
    def test_repeated_startup_no_duplicate_seed(self, test_db):
        """Re-running create_app (init re-runs migrations+seed) adds no rows."""
        counts_before = {
            t: query_one(test_db, f"SELECT count(*) AS n FROM {t}")["n"]
            for t in ("users", "materials", "knowledge_entries")
        }
        app = create_app(Config())
        app.testing = True
        counts_after = {
            t: query_one(test_db, f"SELECT count(*) AS n FROM {t}")["n"]
            for t in ("users", "materials", "knowledge_entries")
        }
        assert counts_before == counts_after
