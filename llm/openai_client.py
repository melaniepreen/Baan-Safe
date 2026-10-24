"""OpenAI SDK client pointed at Mubit. Same rules as llm/client.py.

Registers the app against the gateway base in MUBIT_BASE_URL (compat OpenRouter
prefix by default). Does not read OPENROUTER_API_KEY. Never prints the key.
"""

from __future__ import annotations

import os

from openai import OpenAI

from config.settings import require_decision
from llm.client import _api_key, _base_url, _require_mubit_host


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
