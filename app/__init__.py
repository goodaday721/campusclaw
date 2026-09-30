"""Flask application factory."""
import time
from pathlib import Path

import pymysql
from flask import Flask

from app.config import Config, resolve_upload_root
from app.db.connection import get_connection, run_migration

ROOT = Path(__file__).resolve().parent.parent

MIGRATIONS = [
    "001_initial_schema.sql",
    "002_sessions_knowledge.sql",
    "003_knowledge_chunks.sql",
]

# DB readiness retry: depends_on only orders container start, it does NOT wait
# for MySQL to finish initializing. The api therefore retries connecting.
# Only connection-level errors are retried (refused/reset); configuration
# errors (access denied 1045, unknown database 1049, ...) fail fast.
DB_RETRY_ATTEMPTS = 30
DB_RETRY_INTERVAL_SECONDS = 2.0
DB_RETRYABLE_ERRNOS = {2003, 2013}


def create_app(config: Config | None = None) -> Flask:
    """Create and configure the Flask application."""
    if config is None:
        config = Config()

    app = Flask(__name__)
    app.config["DB"] = config.db_config()
    app.config["QDRANT"] = config.qdrant_config()
    app.config["APP_CONFIG"] = config
    app.config["SESSION_TTL_HOURS"] = config.session_ttl_hours
    app.config["UPLOAD_MAX_SIZE_MB"] = config.upload_max_size_mb
    app.config["UPLOAD_ROOT"] = resolve_upload_root(config.upload_root, ROOT)

    # DB init (migrations + seed on first run). Fails fast — after the retry
    # window expires the process exits so the container restart policy applies.
    _init_db(app.config["DB"])

    # Best-effort chunk backfill for seeded/pre-existing materials. Never blocks
    # startup and never requires Qdrant: chunks make keyword search work at once,
    # embeddings are attempted and marked 'failed' when the gateway is absent.
    _backfill_indexes(app.config["DB"], app.config["QDRANT"], config)

    # Register blueprints
    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.materials import materials_bp
    from app.routes.search import search_bp
    from app.routes.ask import ask_bp
    from app.routes.pages import pages_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(ask_bp)
    app.register_blueprint(pages_bp)

    return app


def _backfill_indexes(db: dict, qcfg: dict, config: Config) -> None:
    """Best-effort startup backfill; any failure is logged and swallowed."""
    try:
        from app.services.indexing import backfill_indexes

        backfill_indexes(db, qcfg, config)
    except Exception as exc:  # noqa: BLE001 — startup must proceed (keyword path)
        print(f"[init] index backfill skipped: {exc}", flush=True)


def _connect_with_retry(db: dict) -> None:
    """Wait for MySQL readiness, then verify connectivity.

    Only connection-level OperationalErrors are retried; anything else
    (bad credentials, bad SQL) fails immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(1, DB_RETRY_ATTEMPTS + 1):
        try:
            conn = get_connection(db)
            conn.close()
            return
        except pymysql.err.OperationalError as exc:
            errno = exc.args[0] if exc.args else None
            if errno not in DB_RETRYABLE_ERRNOS:
                raise
            print(
                f"[init] MySQL not ready (attempt {attempt}/{DB_RETRY_ATTEMPTS}): "
                f"{exc}; retrying in {DB_RETRY_INTERVAL_SECONDS}s",
                flush=True,
            )
            time.sleep(DB_RETRY_INTERVAL_SECONDS)
    raise RuntimeError(
        f"MySQL not reachable after {DB_RETRY_ATTEMPTS} attempts"
    ) from last_exc


def _init_db(db: dict) -> None:
    """Run all migrations and seed if not yet done (after readiness wait)."""
    _connect_with_retry(db)
    conn = get_connection(db)
    try:
        for name in MIGRATIONS:
            run_migration(conn, str(ROOT / "migrations" / name))
        # Seed (idempotent)
        from seeds.seed import seed

        seed(conn)
    finally:
        conn.close()
