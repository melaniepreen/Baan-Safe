"""Read fixture files listed in fixtures/index.json."""

from __future__ import annotations

import json
from pathlib import Path

from contracts.models import CaseState
from paths import ROOT

FIXTURES = ROOT / "fixtures"


def index() -> dict:
    return json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))


def list_entries() -> list[dict]:
    data = index()
    return list(data.get("scenarios") or []) + list(data.get("graduation") or [])


def entry(fixture_id: str) -> dict:
    for item in list_entries():
        if item["id"] == fixture_id:
            return item
    raise KeyError(fixture_id)


def load_fixture(fixture_id: str) -> dict:
    item = entry(fixture_id)
    path = FIXTURES / item["path"]
    return json.loads(path.read_text(encoding="utf-8"))


def load_case(fixture_id: str) -> CaseState:
    payload = load_fixture(fixture_id)
    return CaseState.model_validate(payload["case_state"])


def all_ids() -> list[str]:
    return [item["id"] for item in list_entries()]


SYNTHETIC = FIXTURES / "synthetic"


def synthetic_index() -> dict:
    return json.loads((SYNTHETIC / "index.json").read_text(encoding="utf-8"))


def synthetic_split() -> dict:
    return json.loads((SYNTHETIC / "split.json").read_text(encoding="utf-8"))


def synthetic_ids() -> list[str]:
    return [item["id"] for item in synthetic_index()["calls"]]


def load_synthetic(case_id: str) -> dict:
    path = SYNTHETIC / "calls" / f"{case_id}.json"
    if not path.is_file():
        raise KeyError(case_id)
    return json.loads(path.read_text(encoding="utf-8"))


def iter_synthetic() -> list[dict]:
    return [load_synthetic(case_id) for case_id in synthetic_ids()]
