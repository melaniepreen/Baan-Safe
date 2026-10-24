"""LLM client. Hackathon rule: every model call goes through Mubit.

The client refuses to run unless MUBIT_BASE_URL and MUBIT_API_KEY are set,
and it refuses any host that is not api.mubit.ai or a subdomain of mubit.ai.
It never prints the key. llm.provider_route stays TODO_HUMAN until a human
confirms the route, so a configured URL still does not leave the process.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from config.settings import DecisionRequired, require_decision

_MUBIT_HOSTS = ("api.mubit.ai",)


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


def complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 256,
) -> dict[str, Any]:
    """POST a chat completion to the Mubit OpenAI-compatible prefix.

    Raises before any socket is opened when the URL, the key, the host, or
    llm.provider_route is missing. The key is not included in the error.
    """
    base = _base_url()
    key = _api_key()
    _require_mubit_host(base)
    try:
        require_decision("llm.provider_route")
    except DecisionRequired:
        raise
    if not model:
        raise DecisionRequired(
            "config/decisions.yaml:system2.orchestrator_model is TODO_HUMAN. "
            "A human must name the model before an LLM call."
        )
    url = f"{base}/openai/v1/chat/completions"
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()
