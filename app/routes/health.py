"""Health check route: GET /health (no auth).

Liveness ONLY — deliberately NO database probing. Database availability is
reflected by business requests and api logs; keeping DB state out of the
health check prevents DB jitter from marking a healthy process as down.
"""
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """Return service liveness. Always 200 while the process is serving."""
    return jsonify({"status": "ok"}), 200
