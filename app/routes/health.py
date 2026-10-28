"""Health routes: GET /health (liveness) + GET /health/ready (readiness).

Both are unauthenticated. ``/health`` answers "is the process serving" and never
touches dependencies, so DB jitter cannot restart a healthy process.
``/health/ready`` answers "can this instance serve traffic": it probes MySQL and
Qdrant with a short timeout and returns 503 when either is unreachable.
"""
import time

import requests
from flask import Blueprint, current_app, jsonify

from app.db.connection import get_connection

health_bp = Blueprint("health", __name__)

PROBE_TIMEOUT_SECONDS = 2.0


@health_bp.route("/health", methods=["GET"])
def health():
    """Return service liveness. Always 200 while the process is serving."""
    return jsonify({"status": "ok"}), 200


@health_bp.route("/health/ready", methods=["GET"])
def readiness():
    """Probe dependencies; 200 when all reachable, 503 when any is down."""
    checks = {"db": _probe_db(), "qdrant": _probe_qdrant()}
    healthy = all(item["status"] == "ok" for item in checks.values())
    return (
        jsonify({"status": "ok" if healthy else "degraded", "checks": checks}),
        200 if healthy else 503,
    )


def _probe_db() -> dict:
    started = time.perf_counter()
    try:
        conn = get_connection(current_app.config["DB"])
        conn.close()
    except Exception as exc:  # noqa: BLE001 — readiness reports, never raises
        return {"status": "error", "error": type(exc).__name__}
    return {"status": "ok", "ms": _elapsed_ms(started)}


def _probe_qdrant() -> dict:
    cfg = current_app.config["QDRANT"]
    started = time.perf_counter()
    try:
        resp = requests.get(
            f"http://{cfg['host']}:{cfg['port']}/collections",
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return {"status": "error", "error": type(exc).__name__}
    if resp.status_code >= 400:
        return {"status": "error", "error": f"http {resp.status_code}"}
    return {"status": "ok", "ms": _elapsed_ms(started)}


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
