"""Map BaanSafe gateway env onto the names latte-bench reads.

The key is passed through to a child process and is never printed.
Live calls stay on a mubit.ai host. The free reference mode does not use this.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse, urlunparse

from config.settings import UNSET

SECRET_NAMES = ("MUBIT_API_KEY", "FRONTIER_API_KEY")


class GatewayEnvError(RuntimeError):
    """A live latte-bench launch is missing a name or is pointed off the gateway."""


def _host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.hostname or "").lower()


def _is_mubit(host: str) -> bool:
    return host == "api.mubit.ai" or host.endswith(".mubit.ai")


_COMPAT_V1 = re.compile(r"^/compat/[A-Za-z0-9._-]+/v1$")


def map_base(url: str, name: str = "MUBIT_BASE_URL") -> str:
    """Accept the gateway root this repo already uses, or latte-bench's OpenAI prefix.

    `https://api.mubit.ai` becomes `https://api.mubit.ai/openai/v1`, which is
    the base latte-bench appends `/chat/completions` to. A compat prefix such
    as `https://api.mubit.ai/compat/openrouter/v1` is kept. A query string is
    dropped so a key cannot hide in the URL.
    """
    raw = url.strip()
    if not raw or raw == UNSET:
        raise GatewayEnvError(f"{name} is not set.")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = _host(raw)
    if not _is_mubit(host):
        raise GatewayEnvError(f"{name} host {host!r} is not a Mubit host.")
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/chat/completions"):
        mapped = path[: -len("/chat/completions")]
    elif path.endswith("/openai/v1") or _COMPAT_V1.match(path):
        mapped = path
    elif path == "":
        mapped = "/openai/v1"
    else:
        raise GatewayEnvError(
            f"{name} path {path!r} is not the gateway root, the OpenAI prefix, "
            "or a /compat/{service}/v1 prefix."
        )
    return urlunparse(parsed._replace(path=mapped, params="", query="", fragment=""))


def _required(source: dict[str, str], name: str) -> str:
    value = source.get(name, "").strip()
    if not value or value == UNSET:
        raise GatewayEnvError(f"{name} is not set.")
    return value


def build_live_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Env for `bun run dev` when LATTE_LIVE=1. Values stay in the child only."""
    src = source if source is not None else dict(os.environ)
    base = map_base(_required(src, "MUBIT_BASE_URL"))
    key = _required(src, "MUBIT_API_KEY")
    model = _required(src, "MUBIT_MODEL")
    frontier = _required(src, "FRONTIER_MODEL")
    child = {
        "MUBIT_BASE_URL": base,
        "MUBIT_API_KEY": key,
        "MUBIT_MODEL": model,
        "FRONTIER_MODEL": frontier,
    }
    frontier_base = src.get("FRONTIER_BASE_URL", "").strip()
    if frontier_base:
        child["FRONTIER_BASE_URL"] = map_base(frontier_base, "FRONTIER_BASE_URL")
    frontier_key = src.get("FRONTIER_API_KEY", "").strip()
    if frontier_key:
        child["FRONTIER_API_KEY"] = frontier_key
    extra = src.get("MUBIT_EXTRA_BODY", "").strip()
    if extra:
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError as exc:
            raise GatewayEnvError("MUBIT_EXTRA_BODY must be a JSON object.") from exc
        if not isinstance(parsed, dict):
            raise GatewayEnvError("MUBIT_EXTRA_BODY must be a JSON object.")
        child["MUBIT_EXTRA_BODY"] = extra
    port = src.get("PORT", "").strip()
    if port:
        child["PORT"] = port
    return child


def describe_live_env(env: dict[str, str]) -> str:
    """Names and non-secret values. Secrets are the word `set`."""
    parts: list[str] = []
    for name in (
        "MUBIT_BASE_URL",
        "MUBIT_API_KEY",
        "MUBIT_MODEL",
        "FRONTIER_MODEL",
        "FRONTIER_BASE_URL",
        "FRONTIER_API_KEY",
        "PORT",
    ):
        if name not in env:
            continue
        if name in SECRET_NAMES or name == "MUBIT_EXTRA_BODY":
            parts.append(f"{name}=set")
        else:
            parts.append(f"{name}={env[name]}")
    if "MUBIT_EXTRA_BODY" in env:
        parts.append("MUBIT_EXTRA_BODY=set")
    return " ".join(parts)


def free_child_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Child env for the reference replay. Gateway secrets are removed."""
    child = dict(source if source is not None else os.environ)
    for name in (*SECRET_NAMES, "MUBIT_EXTRA_BODY"):
        child.pop(name, None)
    return child
