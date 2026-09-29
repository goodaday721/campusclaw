"""Application configuration loaded from environment variables."""
import os
from pathlib import Path


class ConfigError(Exception):
    """Raised when a required configuration value is missing or invalid."""


def resolve_upload_root(value: str, root: Path) -> Path:
    """Return the upload root as an absolute path.

    Relative values are resolved against the project root; absolute paths
    (e.g. the in-container /app/uploads) are used as-is.
    """
    p = Path(value)
    return p if p.is_absolute() else (root / p)


class Config:
    """Holds all runtime configuration, validated from environment variables."""

    def __init__(self, env: dict | None = None) -> None:
        source = env if env is not None else os.environ
        # MySQL connection (api shares these with the db service via .env)
        self.db_host = source.get("DB_HOST", "db")
        self.db_port = int(source.get("DB_PORT", "3306"))
        self.db_name = self._require(source, "DB_NAME")
        self.db_user = self._require(source, "DB_USER")
        self.db_password = self._require(source, "DB_PASSWORD")
        self.session_ttl_hours = int(self._require(source, "SESSION_TTL_HOURS"))
        self.session_cookie_name = source.get("SESSION_COOKIE_NAME", "session_id")
        self.port = int(source.get("PORT", "5000"))
        self.upload_max_size_mb = int(source.get("UPLOAD_MAX_SIZE_MB", "50"))
        self.upload_root = source.get("UPLOAD_ROOT", "uploads")

        # Qdrant vector store (internal compose service; optional dependency —
        # keyword search keeps working when it is unreachable).
        self.qdrant_host = source.get("QDRANT_HOST", "qdrant")
        self.qdrant_port = int(source.get("QDRANT_PORT", "6333"))
        self.qdrant_collection = source.get("QDRANT_COLLECTION", "campusclaw_chunks")

        # Model gateway (OpenAI-compatible). Keys are optional at startup:
        # without them keyword search still works; vector/hybrid/ask return 503.
        self.embed_base_url = source.get("EMBED_BASE_URL", "").strip()
        self.embed_api_key = source.get("EMBED_API_KEY", "").strip()
        self.embed_model = source.get("EMBED_MODEL", "")
        self.chat_base_url = source.get("CHAT_BASE_URL", "").strip()
        self.chat_api_key = source.get("CHAT_API_KEY", "").strip()
        self.chat_model = source.get("CHAT_MODEL", "")
        self.gateway_timeout_connect = float(source.get("GATEWAY_TIMEOUT_CONNECT", "5"))
        self.gateway_timeout_read = float(source.get("GATEWAY_TIMEOUT_READ", "30"))

        # Retrieval tuning (lesson-4 fixed values, overridable for tests).
        self.vector_threshold = float(source.get("RETRIEVAL_VECTOR_THRESHOLD", "0.35"))
        self.rrf_k = float(source.get("RRF_K", "60"))
        self.search_path_limit = int(source.get("SEARCH_PATH_LIMIT", "20"))
        self.search_final_limit = int(source.get("SEARCH_FINAL_LIMIT", "10"))
        self.ask_top_k = int(source.get("ASK_TOP_K", "4"))
        # Excerpt length shown in search results (characters).
        self.excerpt_limit = int(source.get("EXCERPT_LIMIT", "200"))

    def db_config(self) -> dict:
        """Connection kwargs for app.db.connection.get_connection."""
        return {
            "host": self.db_host,
            "port": self.db_port,
            "user": self.db_user,
            "password": self.db_password,
            "database": self.db_name,
        }

    def qdrant_config(self) -> dict:
        """Connection kwargs for app.services.vector_store."""
        return {
            "host": self.qdrant_host,
            "port": self.qdrant_port,
            "collection": self.qdrant_collection,
        }

    def embed_configured(self) -> bool:
        """True when the embedding gateway is fully configured."""
        return bool(self.embed_base_url and self.embed_api_key and self.embed_model)

    def chat_configured(self) -> bool:
        """True when the chat gateway is fully configured."""
        return bool(self.chat_base_url and self.chat_api_key and self.chat_model)

    @staticmethod
    def _require(source: dict, key: str) -> str:
        val = source.get(key, "").strip()
        if not val:
            raise ConfigError(
                f"Missing required environment variable: {key}. "
                f"Set it in .env or the environment before starting."
            )
        return val
