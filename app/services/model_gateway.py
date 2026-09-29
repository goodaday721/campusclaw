"""OpenAI-compatible model gateway client (embeddings + chat), server-side only.

All addressing, keys and raw gateway responses stay on the server. Two error
classes let routes distinguish "dependency unavailable" (503) from a rejected
request (4xx). Keys are never logged.
"""
import requests


class GatewayError(Exception):
    """Base class for gateway failures."""


class GatewayUnavailable(GatewayError):
    """Gateway not configured, unreachable, timed out, or returned 5xx → 503."""


class GatewayRejected(GatewayError):
    """Gateway rejected the request as invalid (4xx) → 400."""


def _timeout(config) -> tuple[float, float]:
    return (config.gateway_timeout_connect, config.gateway_timeout_read)


def embed_texts(config, texts: list[str]) -> list[list[float]]:
    """Embed one batch of texts; returns vectors in the SAME order as input.

    Raises GatewayUnavailable when unconfigured/unreachable and GatewayRejected
    on a 4xx response.
    """
    if not texts:
        return []
    if not config.embed_configured():
        raise GatewayUnavailable("embedding gateway is not configured")

    url = config.embed_base_url.rstrip("/") + "/embeddings"
    headers = {
        "Authorization": f"Bearer {config.embed_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": config.embed_model, "input": texts}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout(config))
    except requests.RequestException as exc:
        raise GatewayUnavailable(f"embedding gateway unreachable: {type(exc).__name__}")

    if 500 <= resp.status_code < 600:
        raise GatewayUnavailable(
            f"embedding gateway returned {resp.status_code}"
        )
    if not (200 <= resp.status_code < 300):
        # Never echo the gateway body: it may echo the request or other details.
        raise GatewayRejected(f"embedding gateway rejected request ({resp.status_code})")

    try:
        data = resp.json()
        items = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [list(map(float, item["embedding"])) for item in items]
    except (ValueError, KeyError, TypeError) as exc:
        raise GatewayUnavailable("embedding gateway returned an unreadable response") from exc


def chat(config, messages: list[dict]) -> str:
    """One non-streaming chat completion. messages follow the OpenAI shape.

    Raises GatewayUnavailable when unconfigured/unreachable and GatewayRejected
    on a 4xx response.
    """
    if not config.chat_configured():
        raise GatewayUnavailable("chat gateway is not configured")

    url = config.chat_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.chat_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": config.chat_model, "messages": messages, "stream": False}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout(config))
    except requests.RequestException as exc:
        raise GatewayUnavailable(f"chat gateway unreachable: {type(exc).__name__}")

    if 500 <= resp.status_code < 600:
        raise GatewayUnavailable(f"chat gateway returned {resp.status_code}")
    if not (200 <= resp.status_code < 300):
        raise GatewayRejected(f"chat gateway rejected request ({resp.status_code})")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GatewayUnavailable("chat gateway returned an unreadable response") from exc
