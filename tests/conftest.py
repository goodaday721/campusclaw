"""Pytest fixtures: isolated MySQL test database + seeded app + per-user Bearer clients.

Token-based auth: each fixture logs in via /auth/login, takes the JWT from the
response body and returns a BearerClient that injects
``Authorization: Bearer <jwt>`` into every request.

Test database: a dedicated database (default campusclaw_test) is dropped and
recreated per test. Connection target comes from TEST_DB_* env vars, falling
back to the standard DB_* ones — inside the container (docker compose exec api
pytest) set TEST_DB_HOST=db TEST_DB_USER=root TEST_DB_PASSWORD=$DB_ROOT_PASSWORD.
"""
import os
from pathlib import Path

import pymysql
import pytest

ROOT = Path(__file__).resolve().parent.parent

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "campusclaw_test")

# Test DB credentials may differ from the app's own (e.g. root inside the
# container, because MYSQL_USER is only granted the main database). When
# TEST_DB_* is set it WINS for the whole test env — the app under test must
# use the same credentials to reach the freshly created test database.
os.environ["DB_HOST"] = os.environ.get("TEST_DB_HOST", os.environ.get("DB_HOST", "127.0.0.1"))
os.environ["DB_PORT"] = os.environ.get("TEST_DB_PORT", os.environ.get("DB_PORT", "3306"))
os.environ["DB_NAME"] = TEST_DB_NAME
os.environ["DB_USER"] = os.environ.get("TEST_DB_USER", os.environ.get("DB_USER", "root"))
os.environ["DB_PASSWORD"] = os.environ.get("TEST_DB_PASSWORD", os.environ.get("DB_PASSWORD", ""))
os.environ.setdefault("SESSION_TTL_HOURS", "24")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("PORT", "5000")
os.environ.setdefault("UPLOAD_ROOT", str(ROOT / "uploads"))

# Lesson 4: test Qdrant instance + isolated test collection.
os.environ["QDRANT_HOST"] = os.environ.get("TEST_QDRANT_HOST", "127.0.0.1")
os.environ["QDRANT_COLLECTION"] = os.environ.get(
    "TEST_QDRANT_COLLECTION", "campusclaw_chunks_test"
)

from app.config import Config  # noqa: E402
from app import create_app  # noqa: E402
from app.db.connection import get_connection, run_migration  # noqa: E402
from app.services import model_gateway  # noqa: E402
from seeds.seed import seed  # noqa: E402

MIGRATIONS = [
    "001_initial_schema.sql",
    "002_sessions_knowledge.sql",
    "003_knowledge_chunks.sql",
]

# Deterministic offline fake for the embedding gateway: normalized bag of
# character bigrams over a fixed dimension. Texts sharing bigrams score higher
# by cosine similarity — enough to exercise threshold/filtering/ranking without
# any external network call.
FAKE_DIM = 256


def _fake_embed_texts(config, texts):
    import math

    vectors = []
    for text in texts or []:
        counts = [0.0] * FAKE_DIM
        tokens = list(text) + [text[i : i + 2] for i in range(len(text) - 1)]
        for tok in tokens:
            counts[hash(tok) % FAKE_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in counts)) or 1.0
        vectors.append([v / norm for v in counts])
    return vectors


def _server_config() -> dict:
    """Connection to the MySQL SERVER (no default database)."""
    return {
        "host": os.environ.get("TEST_DB_HOST", os.environ["DB_HOST"]),
        "port": int(os.environ.get("TEST_DB_PORT", os.environ["DB_PORT"])),
        "user": os.environ.get("TEST_DB_USER", os.environ["DB_USER"]),
        "password": os.environ.get("TEST_DB_PASSWORD", os.environ["DB_PASSWORD"]),
    }


@pytest.fixture()
def test_db():
    """Drop + recreate the test database, run migrations + seed, return db cfg."""
    server = pymysql.connect(
        host=_server_config()["host"],
        port=_server_config()["port"],
        user=_server_config()["user"],
        password=_server_config()["password"],
        charset="utf8mb4",
        autocommit=True,
    )
    with server.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
        cur.execute(f"CREATE DATABASE {TEST_DB_NAME} CHARACTER SET utf8mb4")
    server.close()

    db = {**_server_config(), "database": TEST_DB_NAME}
    conn = get_connection(db)
    try:
        for name in MIGRATIONS:
            run_migration(conn, str(ROOT / "migrations" / name))
        seed(conn, upload_root=Path(os.environ["UPLOAD_ROOT"]))
    finally:
        conn.close()

    os.environ["DB_NAME"] = TEST_DB_NAME
    yield db

    server = pymysql.connect(
        host=_server_config()["host"],
        port=_server_config()["port"],
        user=_server_config()["user"],
        password=_server_config()["password"],
        charset="utf8mb4",
        autocommit=True,
    )
    with server.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    server.close()


@pytest.fixture()
def reset_vector_store():
    """Drop + recreate nothingness: delete the test collection per test.

    Startup backfill (inside create_app) recreates it via ensure_collection
    using the fake embedding dimension.
    """
    from app.services import vector_store

    qcfg = Config().qdrant_config()
    client = vector_store._client(qcfg)
    try:
        client.delete_collection(qcfg["collection"])
    except Exception:
        pass
    return qcfg


@pytest.fixture()
def flask_app(test_db, reset_vector_store, monkeypatch):
    """Flask app bound to the test database, with offline fake model gateway."""
    # Patch BEFORE create_app so startup backfill indexes with the fake embed.
    monkeypatch.setattr(model_gateway, "embed_texts", _fake_embed_texts)
    config = Config()
    app = create_app(config)
    app.testing = True
    return app


@pytest.fixture()
def chat_spy(monkeypatch):
    """Record chat gateway calls; reply with a deterministic cited answer."""
    calls = []

    def _fake_chat(config, messages):
        calls.append(messages)
        return "根据班级资料[1]，这是测试回答。"

    monkeypatch.setattr(model_gateway, "chat", _fake_chat)
    return calls


@pytest.fixture()
def app_client(flask_app):
    """Anonymous (not logged in) test client."""
    return flask_app.test_client()


class BearerClient:
    """Wraps a Flask test client and injects ``Authorization: Bearer <jwt>``
    into every request, so call sites keep the plain client.get/post syntax."""

    def __init__(self, client, token: str):
        self._client = client
        self._token = token

    @property
    def token(self) -> str:
        return self._token

    def _kw(self, kwargs: dict) -> dict:
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {self._token}"
        kwargs["headers"] = headers
        return kwargs

    def get(self, path, **kw):
        return self._client.get(path, **self._kw(kw))

    def post(self, path, **kw):
        return self._client.post(path, **self._kw(kw))

    def put(self, path, **kw):
        return self._client.put(path, **self._kw(kw))

    def patch(self, path, **kw):
        return self._client.patch(path, **self._kw(kw))

    def delete(self, path, **kw):
        return self._client.delete(path, **self._kw(kw))

    def open(self, path, **kw):
        return self._client.open(path, **self._kw(kw))


def _logged_in_client(flask_app, username: str, password: str) -> BearerClient:
    """Login and return a BearerClient holding that user's JWT."""
    client = flask_app.test_client()
    resp = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"login failed for {username}: {resp.get_json()}"
    token = resp.get_json()["token"]
    return BearerClient(client, token)


@pytest.fixture()
def teacher_a(flask_app):
    return _logged_in_client(flask_app, "teacher_a", "teacher_a_pass")


@pytest.fixture()
def teacher_b(flask_app):
    return _logged_in_client(flask_app, "teacher_b", "teacher_b_pass")


@pytest.fixture()
def student_a(flask_app):
    return _logged_in_client(flask_app, "student_a", "student_a_pass")


@pytest.fixture()
def student_b(flask_app):
    return _logged_in_client(flask_app, "student_b", "student_b_pass")


# ---- small query helpers for tests (PyMySQL is cursor-based) ----

def query_one(db: dict, sql: str, params: tuple = ()) -> dict | None:
    conn = get_connection(db)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def query_all(db: dict, sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection(db)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def execute(db: dict, sql: str, params: tuple = ()) -> None:
    conn = get_connection(db)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()
