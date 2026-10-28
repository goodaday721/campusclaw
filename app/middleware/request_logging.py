"""One-line JSON access log + request id (lesson-7 ops standard).

Every request emits exactly one JSON line to stdout so container logs stay
machine-readable: ts / level / request_id / method / path / status / ms /
class_id / user_id. The same id is echoed back in ``X-Request-Id`` (incoming
header is reused when present) so a user-visible failure can be traced to one
log line.
"""
import json
import logging
import sys
import time
import uuid

from flask import g, request


def init_request_logging(app) -> None:
    # Silence Werkzeug's default access log so every line in the container log
    # is exactly one JSON record (lesson-7 ops standard).
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @app.before_request
    def _mark_start() -> None:
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        g.request_started = time.perf_counter()

    @app.after_request
    def _write_access_log(resp):
        ident = g.get("request_id") or ""
        resp.headers["X-Request-Id"] = ident
        started = g.get("request_started")
        elapsed = (
            round((time.perf_counter() - started) * 1000, 1)
            if started is not None
            else None
        )
        user = g.get("current_user") or {}
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "level": "INFO",
            "request_id": ident,
            "method": request.method,
            "path": request.path,
            "status": resp.status_code,
            "ms": elapsed,
            "class_id": user.get("classId"),
            "user_id": user.get("userId"),
        }
        sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return resp
