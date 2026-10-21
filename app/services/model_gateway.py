"""OpenAI-compatible model gateway client (embeddings + chat), server-side only.

All addressing, keys and raw gateway responses stay on the server. Two error
classes let routes distinguish "dependency unavailable" (503) from a rejected
request (4xx). Keys are never logged.
"""
import json

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


def chat_with_tools(config, messages: list[dict], tools: list[dict]) -> dict:
    """One non-streaming completion WITH tool declarations (lesson 6 loop).

    Returns {"content": str | None, "tool_calls": [{"id", "name", "arguments"
    (dict)}] | None}. Arguments that fail to parse as JSON are skipped with
    the tool_call dropped (the host treats a malformed proposal as no call —
    the model simply gets no data for it and answers from what it has).
    Raises GatewayUnavailable / GatewayRejected like chat().
    """
    if not config.chat_configured():
        raise GatewayUnavailable("chat gateway is not configured")

    url = config.chat_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.chat_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.chat_model,
        "messages": messages,
        "stream": False,
        "tools": tools,
    }
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
        message = data["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GatewayUnavailable("chat gateway returned an unreadable response") from exc

    calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        name = fn.get("name")
        raw_args = fn.get("arguments") or "{}"
        if not isinstance(name, str) or not name:
            continue
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except ValueError:
            continue
        if not isinstance(args, dict):
            continue
        calls.append({
            "id": call.get("id") or f"call_{len(calls)}",
            "name": name,
            "arguments": args,
        })
    content = message.get("content")
    return {
        "content": content if isinstance(content, str) and content.strip() else None,
        "tool_calls": calls or None,
    }


def chat_stream(config, messages: list[dict]):
    """Yield text deltas from a streaming chat completion (OpenAI compatible).

    Sends ``"stream": true`` and parses the SSE ``data:`` lines; ``[DONE]``
    ends the stream. Each yielded value is one content delta (str). Raises
    GatewayUnavailable when unconfigured/unreachable and GatewayRejected on a
    4xx response. An exception after deltas were already yielded means the
    stream broke mid-answer (the caller treats it as an interrupted answer).
    """
    if not config.chat_configured():
        raise GatewayUnavailable("chat gateway is not configured")

    url = config.chat_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.chat_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": config.chat_model, "messages": messages, "stream": True}
    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=_timeout(config), stream=True
        )
    except requests.RequestException as exc:
        raise GatewayUnavailable(f"chat gateway unreachable: {type(exc).__name__}")

    # Status errors surface BEFORE any delta is yielded, so the route can
    # still answer with a normal JSON error instead of a broken SSE stream.
    if 500 <= resp.status_code < 600:
        resp.close()
        raise GatewayUnavailable(f"chat gateway returned {resp.status_code}")
    if not (200 <= resp.status_code < 300):
        resp.close()
        raise GatewayRejected(f"chat gateway rejected request ({resp.status_code})")

    try:
        # Iterate BYTES and decode whole lines only: iter_lines(decode_unicode=
        # True) decodes per chunk (ISO-8859-1 by default), which splits
        # multi-byte UTF-8 characters at chunk boundaries and corrupts JSON.
        for raw_line in resp.iter_lines():
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else str(raw_line)
            )
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError as exc:
                raise GatewayUnavailable(
                    f"chat gateway returned an unreadable stream chunk "
                    f"({exc.__class__.__name__}: {exc}); head={data[:80]!r}"
                )
            # Heartbeat/keep-alive frames carry an empty choices list — skip.
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                yield delta
    except requests.RequestException as exc:
        raise GatewayUnavailable(
            f"chat gateway stream interrupted: {type(exc).__name__}"
        ) from exc
    finally:
        resp.close()
