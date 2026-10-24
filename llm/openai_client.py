"""OpenAI SDK client pointed at Mubit. Same rules as llm/client.py.

Registers the app against the gateway base in MUBIT_BASE_URL (compat OpenRouter
prefix by default). Does not read OPENROUTER_API_KEY. Never prints the key.

`chat` wraps `chat.completions.create` and emits the same `mubit_chat`
TraceEvent as `llm.client.complete`. Prefer `llm.client.complete` for the
System 2 path; this helper is for SDK callers that still need a visible hop.
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from openai import OpenAI

from config.settings import require_decision
from llm.client import (
    _api_key,
    _base_url,
    _require_mubit_host,
    emit_mubit_chat_trace,
)


def make_client() -> OpenAI:
    """Build an OpenAI client for the registered Mubit OpenAI-compatible prefix."""
    require_decision("llm.provider_route")
    base = _base_url()
    _require_mubit_host(base)
    return OpenAI(
        base_url=base,
        api_key=_api_key(),
    )


def registered_base_url() -> str:
    """Return the base URL the app is registered against (no trailing slash)."""
    require_decision("llm.provider_route")
    base = _base_url()
    _require_mubit_host(base)
    return base


def chat(
    messages: list[dict[str, str]],
    model: str,
    *,
    max_tokens: int = 256,
    timeout: float = 30.0,
    temperature: float | None = None,
    seed: int | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Chat completion via the OpenAI SDK. Emits `mubit_chat`; never logs the key."""
    require_decision("llm.provider_route")
    base = _base_url()
    host = _require_mubit_host(base)
    client = make_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if seed is not None:
        kwargs["seed"] = seed

    started_at = datetime.now(timezone.utc)
    t0 = perf_counter()
    status = "ok"
    tokens_in: int | None = None
    tokens_out: int | None = None
    try:
        response = client.chat.completions.create(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt = getattr(usage, "prompt_tokens", None)
            completion = getattr(usage, "completion_tokens", None)
            tokens_in = int(prompt) if prompt is not None else None
            tokens_out = int(completion) if completion is not None else None
        return response.model_dump()
    except Exception as exc:
        status = _sdk_status(exc)
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
        )


def _sdk_status(exc: BaseException) -> str:
    """Map an SDK/httpx error to a short status class. Never include secrets."""
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return "http_429"
    if isinstance(status_code, int) and status_code >= 400:
        return f"http_{status_code}"
    name = type(exc).__name__
    if "Timeout" in name:
        return "timeout"
    return "sdk_error"
