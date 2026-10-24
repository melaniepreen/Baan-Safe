"""Committed public-data snapshots.

Raw responses stay under ``data/raw/`` (gitignored). These JSON files are the
small offline copy the demo reads when a live call fails. A snapshot that
contains a credential is refused.
"""

from __future__ import annotations

import json
import re

from ingest.common import scrub
from paths import ROOT

SNAPSHOT_DIR = ROOT / "data" / "snapshots"

_FORBIDDEN = (
    "awsaccesskeyid",
    "x-amz-security-token",
    "gistda_api_key=",
    "api_key=",
    "signature=",
)


def snapshot_path(name: str):
    safe = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not safe:
        raise ValueError("snapshot name is empty")
    return SNAPSHOT_DIR / f"{safe}.json"


def read_snapshot(name: str) -> dict | None:
    path = snapshot_path(name)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def write_snapshot(name: str, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    text = scrub(text)
    lowered = text.lower()
    for marker in _FORBIDDEN:
        if marker in lowered:
            raise RuntimeError(f"refusing to store snapshot {name}: credential marker")
    path = snapshot_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
