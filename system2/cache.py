"""System 2 reply cache: `S2_IMPL=cache`.

Cache-first completer for the Nemotron orchestrator so a demo survives a
Mubit timeout. The default key is exact: sha256 over the model id and the
full message list (the same key the RL loop uses), so a reply is reused only
when the case, the memory context, and the prompt are byte-identical.
`S2_CACHE_KEY=case` drops `case_id`, `memory`, and `resources` from the user
payload before hashing, so the same transcript, fields, triggers, and handoff
hit again on a long-running server whose store and ledger have moved. A hit
under that mode is traced as `host=s2_cache/case`. Nothing is fuzzy-matched
in either mode.

Lookup order: `S2_CACHE_PATH` (default `fixtures/s2_cache/demo.jsonl`,
committed) then `S2_CACHE_RECORD_PATH` (optional, written on misses; later
rows win). A hit emits a `mubit_chat` trace with `host=s2_cache
status=cache_hit` and opens no socket. A miss goes through
`llm.client.complete` (Mubit only) and, when a record path is set, appends
`{"key", "reply"}` so the next identical turn is a hit. Without Mubit
credentials a miss raises `ValueError`, which the orchestrator turns into the
safe supervisor-escalation fallback.

Record the demo cache after memory is seeded: the memory summaries are part
of the prompt, so a reply recorded against an empty store will not match the
same transcript on a seeded one.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from paths import ROOT

DEFAULT_PATH = ROOT / "fixtures" / "s2_cache" / "demo.jsonl"
HOST = "s2_cache"

_loaded: dict[tuple[tuple[str, float], ...], dict[str, dict]] = {}


# Payload keys dropped by `S2_CACHE_KEY=case`: the per-request id and the two
# inputs that drift between otherwise identical turns on a long-running
# server (the memory store grows after every case; the dispatch ledger moves).
_CASE_KEY_DROPS = ("case_id", "memory", "resources")


def key_mode() -> str:
    mode = os.environ.get("S2_CACHE_KEY", "exact").strip().lower() or "exact"
    if mode not in {"exact", "case"}:
        raise ValueError(f"S2_CACHE_KEY must be exact or case, got {mode!r}")
    return mode


def _case_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages with case_id, memory, and resources removed from the JSON
    user payload. Non-JSON content is left as is."""
    out: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if message.get("role") == "user" and isinstance(content, str):
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                for name in _CASE_KEY_DROPS:
                    payload.pop(name, None)
                message = {**message, "content": json.dumps(payload, sort_keys=True)}
        out.append(message)
    return out


def cache_key(model: str | None, messages: list[dict[str, Any]], mode: str = "exact") -> str:
    """sha256 over the model and the messages. `exact` hashes them as sent;
    `case` first drops case_id, memory, and resources from the user payload."""
    if mode == "case":
        messages = _case_messages(messages)
    elif mode != "exact":
        raise ValueError(f"unknown cache key mode {mode!r}")
    raw = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path() -> Path:
    raw = os.environ.get("S2_CACHE_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_PATH


def record_path() -> Path | None:
    raw = os.environ.get("S2_CACHE_RECORD_PATH", "").strip()
    return Path(raw) if raw else None


def _paths() -> list[Path]:
    paths = [cache_path()]
    extra = record_path()
    if extra is not None and extra != paths[0]:
        paths.append(extra)
    return paths


def _read(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("key")
            reply = row.get("reply")
            if isinstance(key, str) and isinstance(reply, dict):
                out[key] = reply
    return out


def load() -> dict[str, dict]:
    """Merged cache, re-read when any file's mtime changes."""
    paths = _paths()
    stamp = tuple((str(p), p.stat().st_mtime if p.is_file() else -1.0) for p in paths)
    cached = _loaded.get(stamp)
    if cached is not None:
        return cached
    merged: dict[str, dict] = {}
    for path in paths:
        merged.update(_read(path))
    _loaded.clear()
    _loaded[stamp] = merged
    return merged


def size() -> int:
    return len(load())


def live_available() -> bool:
    return bool(os.environ.get("MUBIT_API_KEY", "").strip()) and bool(
        os.environ.get("MUBIT_BASE_URL", "").strip()
    )


def record(key: str, reply: dict) -> bool:
    path = record_path()
    if path is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"key": key, "reply": reply}, ensure_ascii=False) + "\n")
    return True


def completer(messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> dict:
    """Cache hit, else one Mubit call (recorded when a record path is set)."""
    from llm.client import REPLY_REQUEST_ID, REPLY_SERVED_BY, complete, emit_mubit_chat_trace

    mode = key_mode()
    key = cache_key(model, messages, mode)
    case_id = str(kwargs.get("case_id") or "s2_cache")
    hit = load().get(key)
    if hit is not None:
        host = HOST if mode == "exact" else f"{HOST}/{mode}"
        emit_mubit_chat_trace(
            case_id=case_id,
            model=model,
            latency_ms=0,
            status="cache_hit",
            host=host,
            request_id=hit.get(REPLY_REQUEST_ID),
            recorded=True,
            served_by=hit.get(REPLY_SERVED_BY),
        )
        return hit
    if not live_available():
        # No socket, no invented hop: the orchestrator falls back safely.
        raise ValueError("s2 cache miss and no Mubit credentials")
    reply = complete(messages, model=model, **kwargs)
    record(key, reply)
    return reply
