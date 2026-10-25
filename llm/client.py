"""LLM client. Hackathon rule: every model call goes through Mubit.

The client refuses to run unless MUBIT_BASE_URL and MUBIT_API_KEY are set,
and it refuses any host that is not api.mubit.ai or a subdomain of mubit.ai.
system2.hosting is OpenRouter behind that gateway. A base of
https://api.mubit.ai/compat/openrouter/v1 is posted to as
{base}/chat/completions. The gateway root still maps to /openai/v1.
This module does not read OPENROUTER_API_KEY and it does not call
openrouter.ai. It never prints the key. llm.provider_route is mubit.
A call still needs system2.orchestrator_model.

Each successful or failed chat POST emits a TraceEvent stage `mubit_chat`
(model, latency_ms, status class). Config refusals before a socket opens
do not emit.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from config.settings import DecisionRequired, require_decision
from contracts.models import TraceEvent
from trace import emit

_MUBIT_HOSTS = ("api.mubit.ai",)
_COMPAT_V1 = re.compile(r"^/compat/[A-Za-z0-9._-]+/v1$")
# Mubit's id for one call, on every answer it sends (success, provider error,
# or its own error). It is what the console's Requests filter and Mubit
# support take. `mreq_` plus 32 hex digits.
REQUEST_ID_HEADER = "x-middleware-request-id"
REPLY_REQUEST_ID = "mubit_request_id"
_MREQ = re.compile(r"^mreq_[0-9a-f]{32}$")


def _base_url() -> str:
    base = os.environ.get("MUBIT_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "LLM calls must go through Mubit. MUBIT_BASE_URL is not set. "
            "Refusing to call any other host."
        )
    return base


def _api_key() -> str:
    key = os.environ.get("MUBIT_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "LLM calls must go through Mubit. MUBIT_API_KEY is not set. "
            "Refusing the call."
        )
    return key


def chat_completions_url(base: str) -> str:
    """OpenAI chat URL for a Mubit gateway root or an already-versioned prefix.

    `https://api.mubit.ai` becomes `.../openai/v1/chat/completions`.
    `https://api.mubit.ai/compat/openrouter/v1` becomes
    `.../compat/openrouter/v1/chat/completions`. A query string is dropped.
    """
    parsed = urlparse(base if "://" in base else f"https://{base}")
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/chat/completions"):
        mapped = path
    elif path == "":
        mapped = "/openai/v1/chat/completions"
    elif path == "/openai/v1" or _COMPAT_V1.match(path):
        mapped = f"{path}/chat/completions"
    else:
        raise RuntimeError(
            f"MUBIT_BASE_URL path {path!r} is not the gateway root or a "
            "Mubit OpenAI-compatible prefix."
        )
    return urlunparse(parsed._replace(path=mapped, params="", query="", fragment=""))


def _require_mubit_host(base: str) -> str:
    parsed = urlparse(base if "://" in base else f"https://{base}")
    host = (parsed.hostname or "").lower()
    allowed = host in _MUBIT_HOSTS or host.endswith(".mubit.ai")
    if not allowed:
        raise RuntimeError(
            f"MUBIT_BASE_URL host {host!r} is not a Mubit host. "
            "Refusing the call. LLM traffic is not sent to any other provider."
        )
    return host


def request_id_from(headers: Any) -> str | None:
    """The `mreq_…` id from a Mubit answer's headers, or None when absent or
    malformed. Never a key: the header holds only the id."""
    try:
        raw = headers.get(REQUEST_ID_HEADER)
    except AttributeError:
        return None
    value = str(raw or "").strip()
    return value if _MREQ.match(value) else None


def emit_mubit_chat_trace(
    *,
    case_id: str,
    model: str | None,
    latency_ms: int,
    status: str,
    host: str,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    started_at: datetime | None = None,
    request_id: str | None = None,
    recorded: bool = False,
) -> None:
    """Append one mubit_chat TraceEvent. Never include a key or bearer.

    `request_id` is Mubit's id for the call. `recorded=True` marks a cache
    replay, where the id belongs to the call that was recorded, not to a hop
    made now.
    """
    notes = f"mubit chat host={host} status={status}"
    if request_id:
        notes += f" request_id={request_id}" + (" (recorded)" if recorded else "")
    emit(
        TraceEvent(
            case_id=case_id or "mubit",
            stage="mubit_chat",
            started_at=started_at or datetime.now(timezone.utc),
            latency_ms=max(0, latency_ms),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
            notes=notes,
        )
    )


def complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 256,
    *,
    timeout: float = 30.0,
    temperature: float | None = None,
    seed: int | None = None,
    reasoning: dict | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """POST a chat completion to the Mubit OpenAI-compatible prefix.

    Raises before any socket is opened when the URL, the key, the host, or
    llm.provider_route is missing. The key is not included in the error.
    A socket attempt always records a `mubit_chat` trace (ok or error class).
    """
    base = _base_url()
    key = _api_key()
    host = _require_mubit_host(base)
    try:
        require_decision("llm.provider_route")
    except DecisionRequired:
        raise
    if not model:
        raise DecisionRequired(
            "config/decisions.yaml:system2.orchestrator_model is TODO_HUMAN. "
            "A human must name the model before an LLM call."
        )
    url = chat_completions_url(base)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if seed is not None:
        body["seed"] = seed
    if reasoning is not None:
        body["reasoning"] = reasoning
    if case_id:
        # Mubit groups a conversation's calls into one session by
        # metadata.session_id and holds adapter test cases out by session, so a
        # case's turns stay together and held-out tests are other cases.
        body["metadata"] = {"session_id": case_id[:200]}

    started_at = datetime.now(timezone.utc)
    t0 = perf_counter()
    status = "ok"
    tokens_in: int | None = None
    tokens_out: int | None = None
    request_id: str | None = None
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
        request_id = request_id_from(response.headers)
        code = response.status_code
        if code == 429:
            status = "http_429"
        elif code >= 400:
            status = f"http_{code}"
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            tokens_in = int(prompt) if prompt is not None else None
            tokens_out = int(completion) if completion is not None else None
        if request_id and isinstance(data, dict):
            # Ride along on the reply so a cache that stores it can replay it.
            data[REPLY_REQUEST_ID] = request_id
        return data
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        status = "http_429" if code == 429 else f"http_{code}"
        raise
    except httpx.TimeoutException:
        status = "timeout"
        raise
    except httpx.HTTPError:
        status = "transport_error"
        raise
    finally:
        emit_mubit_chat_trace(
            case_id=case_id or "mubit",
            model=model,
            latency_ms=int((perf_counter() - t0) * 1000),
            status=status,
            host=host,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            started_at=started_at,
            request_id=request_id,
        )
