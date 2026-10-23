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
