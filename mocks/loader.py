"""Load mock memory, stub outcomes, and fictional resources as Pydantic models."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from contracts.models import Correction, MemoryItem, Outcome
from paths import ROOT

MOCKS = ROOT / "mocks"


class ResourceUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    name: str
    district: str
    capacity: int | None = None
    available: int | None = None
    status: str


class ResourcesSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boats: list[ResourceUnit] = Field(default_factory=list)
    ambulances: list[ResourceUnit] = Field(default_factory=list)
    shelters: list[ResourceUnit] = Field(default_factory=list)
    welfare_points: list[ResourceUnit] = Field(default_factory=list)


def corrections_path() -> Path:
    raw = os.environ.get("MOCK_CORRECTIONS_PATH", "").strip()
    if raw:
        return Path(raw)
    return ROOT / "data" / "processed" / "corrections.jsonl"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_memory(fixture_id: str) -> list[MemoryItem]:
    path = MOCKS / "memory_context" / f"{fixture_id}.json"
    if not path.exists():
        items: list[MemoryItem] = []
    else:
        items = [MemoryItem.model_validate(row) for row in _read_json(path)]
    items.extend(runtime_correction_items(fixture_id))
    return items


def load_s1_stub(fixture_id: str) -> Outcome:
    path = MOCKS / "s1_stub" / f"{fixture_id}.json"
    return Outcome.model_validate(_read_json(path))


def load_s2_stub(fixture_id: str) -> Outcome:
    path = MOCKS / "s2_stub" / f"{fixture_id}.json"
    return Outcome.model_validate(_read_json(path))


def has_s1_stub(fixture_id: str) -> bool:
    return (MOCKS / "s1_stub" / f"{fixture_id}.json").exists()


def has_s2_stub(fixture_id: str) -> bool:
    return (MOCKS / "s2_stub" / f"{fixture_id}.json").exists()


def load_resources() -> ResourcesSnapshot:
    return ResourcesSnapshot.model_validate(_read_json(MOCKS / "resources.json"))


def correction_pairs() -> list[tuple[str, str]]:
    index_path = ROOT / "fixtures" / "index.json"
    if not index_path.exists():
        return []
    index = _read_json(index_path)
    pairs = []
    for pair in index.get("correction_pairs") or []:
        pairs.append((pair["a"], pair["b"]))
    return pairs


def pair_source_for(fixture_id: str) -> str | None:
    """Return the Cxx-a id whose corrections should surface on this fixture."""
    for left, right in correction_pairs():
        if fixture_id == right:
            return left
    return None


def append_correction(correction: Correction) -> None:
    path = corrections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(correction.model_dump_json() + "\n")


def read_corrections() -> list[Correction]:
    path = corrections_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(Correction.model_validate_json(line))
    return rows


def runtime_correction_items(fixture_id: str) -> list[MemoryItem]:
    """Turn JSONL corrections into MemoryItems.

    A correction written on Cxx-a is retrieved for Cxx-b. The static mock file
    for Cxx-a does not contain a correction item.
    """
    # A case sees corrections written on itself. Cxx-b also sees corrections
    # written on Cxx-a, which is how the demo pair works.
    source_id = pair_source_for(fixture_id)
    wanted = {fixture_id}
    if source_id:
        wanted.add(source_id)
    return [
        _correction_item(correction)
        for correction in read_corrections()
        if correction.case_id in wanted
    ]


def _correction_item(correction: Correction) -> MemoryItem:
    return MemoryItem(
        memory_id=f"runtime:{correction.correction_id}",
        kind="correction",
        summary=(
            f"Correction on {correction.case_id}: {correction.field} "
            f"{correction.old_value} → {correction.new_value}. {correction.reason}"
        ),
        relevance=1.0,
        source_case_id=correction.case_id,
    )
