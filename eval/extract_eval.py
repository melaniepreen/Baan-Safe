"""Score the System 1 keyword extractor against the hand-filled fixture fields.

`make extract-eval`. Each fixture transcript goes through system1.extract.
The result is compared field by field with the fixture's case_state.fields
and policy_flags, then both versions go through the gateway pre-check.
An unsafe miss is a fixture whose hand fields route to System 2 while the
extracted fields route to System 1. Writes eval/out/extract.md.
"""

from __future__ import annotations

from contracts.models import CaseState, ExtractedFields, System
from fixtures.load import all_ids, load_case, load_fixture
from gateway.chooser import choose
from paths import ROOT
from system1.extract import extract

OUT = ROOT / "eval" / "out" / "extract.md"
FLAGS = {"safeguarding", "conflicting_evidence"}
MIN_LOCATION_CONFIDENCE = 0.7


def _usable(fields: ExtractedFields) -> bool:
    return fields.location is not None and (fields.location_confidence or 0) >= MIN_LOCATION_CONFIDENCE


def _location_agrees(hand: ExtractedFields, got: ExtractedFields) -> bool:
    if _usable(hand) != _usable(got):
        return False
    if not _usable(hand):
        return True
    district = got.location.split(",")[0].strip().lower()
    return bool(district) and district in hand.location.lower()


def _with(case: CaseState, fields: ExtractedFields, flags: list[str]) -> CaseState:
    return case.model_copy(update={"fields": fields, "policy_flags": flags})


def score(fixture_id: str) -> dict:
    case = load_case(fixture_id)
    hand = case.fields
    got, got_flags = extract(case.transcript)
    checks = {
        "needs": set(got.needs) == set(hand.needs),
        "people_count": got.people_count == hand.people_count,
        "location": _location_agrees(hand, got),
        "vulnerable": set(got.vulnerable) == set(hand.vulnerable),
        "danger": set(got.danger) == set(hand.danger),
        "medical": got.medical == hand.medical,
        "flags": FLAGS & set(got_flags) == FLAGS & set(case.policy_flags),
    }
    hand_system, _ = choose(case)
    got_system, got_triggers = choose(_with(case, got, [*got_flags, "keyword_extraction"]))
    return {
        "id": fixture_id,
        "checks": checks,
        "expected_system": load_fixture(fixture_id)["expected"]["system"],
        "hand_system": hand_system.value,
        "extracted_system": got_system.value,
        "unsafe_miss": hand_system is System.system_2 and got_system is System.system_1,
        "over_escalation": hand_system is System.system_1 and got_system is System.system_2,
        "triggers": got_triggers,
    }


def report(rows: list[dict]) -> str:
    n = len(rows)
    fields = list(rows[0]["checks"])
    lines = [
        "# Keyword extractor vs hand-filled fixture fields",
        "",
        f"Fixtures: {n}. Extraction reads caller turns only. English only.",
        "",
        "| Field | Agree | Rate |",
        "|---|---|---|",
    ]
    for name in fields:
        agree = sum(row["checks"][name] for row in rows)
        lines.append(f"| {name} | {agree}/{n} | {agree / n:.2f} |")
    all_fields = sum(all(row["checks"].values()) for row in rows)
    same_route = sum(row["hand_system"] == row["extracted_system"] for row in rows)
    unsafe = [row["id"] for row in rows if row["unsafe_miss"]]
    over = [row["id"] for row in rows if row["over_escalation"]]
    lines += [
        f"| all fields | {all_fields}/{n} | {all_fields / n:.2f} |",
        "",
        f"Pre-check route agrees with the hand fields: {same_route}/{n}.",
        f"Unsafe misses (hand fields go to System 2, extracted go to System 1): {len(unsafe)} {unsafe}",
        f"Over-escalations (hand fields go to System 1, extracted go to System 2): {len(over)} {over}",
        "",
        "| Fixture | Expected | Hand route | Extracted route | Mismatched fields |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        missed = ", ".join(name for name, ok in row["checks"].items() if not ok) or "-"
        lines.append(
            f"| {row['id']} | {row['expected_system']} | {row['hand_system']} "
            f"| {row['extracted_system']} | {missed} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = [score(fixture_id) for fixture_id in all_ids()]
    text = report(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
