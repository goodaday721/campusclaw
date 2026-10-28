"""Lesson-7 skeleton baseline: /health, /health/ready and request-id logging."""
import json


def test_liveness_is_plain_ok(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_readiness_reports_each_dependency(app_client):
    resp = app_client.get("/health/ready")
    assert resp.status_code in (200, 503), resp.status_code
    body = resp.get_json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["checks"]) == {"db", "qdrant"}
    assert body["checks"]["db"]["status"] in ("ok", "error")
    assert body["checks"]["qdrant"]["status"] in ("ok", "error")
    # Status code must agree with the per-check verdict.
    expected = 200 if all(c["status"] == "ok" for c in body["checks"].values()) else 503
    assert resp.status_code == expected


def test_request_id_is_echoed_and_logged(app_client, capsys):
    resp = app_client.get("/health", headers={"X-Request-Id": "trace-lesson7"})
    assert resp.headers["X-Request-Id"] == "trace-lesson7"

    lines = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    assert lines, "no JSON access log emitted"
    record = json.loads(lines[-1])
    assert record["request_id"] == "trace-lesson7"
    assert record["path"] == "/health"
    assert record["status"] == 200
    for key in ("ts", "level", "method", "ms", "class_id", "user_id"):
        assert key in record, f"missing log field {key}"
