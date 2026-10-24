"""LLM client. Hackathon rule: every model call goes through Mubit.

The client refuses to run unless MUBIT_BASE_URL and MUBIT_API_KEY are set,
and it refuses any host that is not api.mubit.ai or a subdomain of mubit.ai.
system2.hosting is OpenRouter behind that gateway. A base of
https://api.mubit.ai/compat/openrouter/v1 is posted to as
{base}/chat/completions. The gateway root still maps to /openai/v1.
This module does not read OPENROUTER_API_KEY and it does not call
openrouter.ai. It never prints the key. llm.provider_route is mubit.
A call still needs system2.orchestrator_model.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from config.settings import DecisionRequired, require_decision

_MUBIT_HOSTS = ("api.mubit.ai",)
_COMPAT_V1 = re.compile(r"^/compat/[A-Za-z0-9._-]+/v1$")


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


def complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 256,
    *,
    timeout: float = 30.0,
    temperature: float | None = None,
    seed: int | None = None,
    reasoning: dict | None = None,
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
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
