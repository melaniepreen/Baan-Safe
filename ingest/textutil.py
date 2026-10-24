"""Short public summaries. No article bodies, no phone numbers, no national ids."""

from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_PHONE = re.compile(r"(?:\+66|0)\d[\d\s-]{7,12}\d")
_NID = re.compile(r"\b\d{13}\b")


def clip(text: str | None, limit: int = 280) -> str:
    raw = html.unescape(text or "")
    raw = _TAG.sub(" ", raw)
    raw = _PHONE.sub("[redacted]", raw)
    raw = _NID.sub("[redacted]", raw)
    raw = " ".join(raw.split())
    if len(raw) > limit:
        return raw[: limit - 1].rstrip() + "…"
    return raw


def as_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
