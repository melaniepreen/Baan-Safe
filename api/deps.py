"""Implementation switches. Each owner flips only their own variable."""

from __future__ import annotations

import os

from fastapi import HTTPException

from ingest.db import db_exists


def _value(name: str, default: str) -> str:
    return os.environ.get(name, default).strip().lower() or default


def s1_impl() -> str:
    return _value("S1_IMPL", "stub")


def s2_impl() -> str:
    return _value("S2_IMPL", "stub")


def memory_impl() -> str:
    return _value("MEMORY_IMPL", "mock")


def enrich_impl() -> str:
    raw = os.environ.get("ENRICH_IMPL", "").strip().lower()
    if raw:
        return raw
    return "data" if db_exists() else "off"


def impl_snapshot() -> dict[str, str]:
    return {
        "S1_IMPL": s1_impl(),
        "S2_IMPL": s2_impl(),
        "MEMORY_IMPL": memory_impl(),
        "ENRICH_IMPL": enrich_impl(),
    }


def not_ready(owner: str, exc: Exception | None = None) -> HTTPException:
    detail = f"not implemented yet — owner: {owner}"
    if exc is not None:
        text = str(exc)
        if "not implemented yet" in text:
            detail = text
        else:
            detail = f"{detail}. {text}"
    return HTTPException(status_code=501, detail=detail)
