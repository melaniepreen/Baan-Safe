"""Score the System 1 keyword extractor. `make extract-eval`.

Tuning set: each fixture transcript goes through system1.extract and is
compared field by field with the hand-filled case_state.fields and
policy_flags. Held-out set: the scripted sim callers (sim/callers), whose
hidden persona gives the true needs, vulnerability, and whether the district
was said. Neither set is extracted on the live demo path.

For every case the reference route is the gateway pre-check on the true
fields, and the extracted route is the pre-check on the extracted fields.
When the extracted case lands in System 1, System 1 and the router run on it.
An unsafe answer is a case whose true fields go to System 2 but whose
extracted fields get a System 1 answer with requires_human false.
Writes eval/out/extract.md.
"""

from __future__ import annotations

from contracts.models import CaseState, ExtractedFields, Need, System, TranscriptTurn
from fixtures.load import all_ids, load_case
from gateway.chooser import choose
from memory.adapter import retrieve
from paths import ROOT
from router.merge import merge
from sim.callers import CATALOG, N_TURNS, compose
from sim.env import RECEIVED_AT
from system1.decide import decide
from system1.extract import extract

OUT = ROOT / "eval" / "out" / "extract.md"
FLAGS = {"safeguarding", "conflicting_evidence"}
MIN_LOCATION_CONFIDENCE = 0.7
SIM_VULNERABLE = {"infant": "child", "older household member": "elderly"}
SIM_LOCATION_CONFIDENCE = 0.85


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


def _outcome(truth: CaseState, got: CaseState) -> dict:
    truth_system, _ = choose(truth)
    got_system, _ = choose(got)
    answer = "-"
    unsafe = False
    if got_system is System.system_1:
        got.memory_context = retrieve(got)
        decision = merge(got, decide(got))
        human = decision.requires_human
        answer = f"{decision.next_action.value}{' +human' if human else ''}"
        unsafe = truth_system is System.system_2 and not human
    return {
        "truth_system": truth_system.value,
        "extracted_system": got_system.value,
        "s1_answer": answer,
        "unsafe": unsafe,
    }


def score_fixture(fixture_id: str) -> dict:
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
    extracted = _with(case, got, [*got_flags, "keyword_extraction"])
    return {"id": fixture_id, "checks": checks, **_outcome(case, extracted)}


def score_sim(spec) -> dict:
    persona = spec.persona
    transcript = [
        TranscriptTurn(t_ms=index * 2000, speaker="caller", text=compose(spec, index).public_text)
        for index in range(N_TURNS)
    ]
    said_district = "omits_location" not in spec.traits
    truth_fields = ExtractedFields(
        location=persona.location if said_district else None,
        location_confidence=SIM_LOCATION_CONFIDENCE if said_district else None,
        vulnerable=[SIM_VULNERABLE.get(tag, tag) for tag in persona.vulnerable],
        needs=[Need(need) for need in persona.true_needs],
    )
    truth = CaseState(
        case_id=f"SIM-{spec.combo_id}",
        caller_id_hash=persona.caller_id,
        transcript=transcript,
        fields=truth_fields,
        received_at=RECEIVED_AT,
    )
    got, got_flags = extract(transcript)
    extracted = _with(truth, got, [*got_flags, "keyword_extraction"])
    return {
        "id": spec.combo_id,
        "true_needs": ", ".join(persona.true_needs),
        "got_needs": ", ".join(need.value for need in got.needs) or "-",
        **_outcome(truth, extracted),
    }


def _summary(rows: list[dict], label: str) -> list[str]:
    n = len(rows)
    same = sum(row["truth_system"] == row["extracted_system"] for row in rows)
    to_s1 = [
        row["id"]
        for row in rows
        if row["truth_system"] == "system_2" and row["extracted_system"] == "system_1"
    ]
    over = [
        row["id"]
        for row in rows
        if row["truth_system"] == "system_1" and row["extracted_system"] == "system_2"
    ]
    unsafe = [row["id"] for row in rows if row["unsafe"]]
    return [
        f"{label} pre-check route agrees with the true fields: {same}/{n}.",
        f"Should be System 2, routed to System 1: {len(to_s1)} {to_s1}",
        f"Unsafe (should be System 2, System 1 answered with no human): {len(unsafe)} {unsafe}",
        f"Over-escalations (should be System 1, routed to System 2): {len(over)} {over}",
    ]


def report(fixture_rows: list[dict], sim_rows: list[dict]) -> str:
    n = len(fixture_rows)
    lines = [
        "# Keyword extractor",
        "",
        "Extraction reads caller turns only. English only.",
        "",
        f"## Tuning set: {n} fixtures vs hand-filled fields",
        "",
        "| Field | Agree | Rate |",
        "|---|---|---|",
    ]
    for name in fixture_rows[0]["checks"]:
        agree = sum(row["checks"][name] for row in fixture_rows)
        lines.append(f"| {name} | {agree}/{n} | {agree / n:.2f} |")
    all_fields = sum(all(row["checks"].values()) for row in fixture_rows)
    lines += [f"| all fields | {all_fields}/{n} | {all_fields / n:.2f} |", ""]
    lines += _summary(fixture_rows, "Fixtures:")
    lines += [
        "",
        "| Fixture | True route | Extracted route | System 1 answer | Mismatched fields |",
        "|---|---|---|---|---|",
    ]
    for row in fixture_rows:
        missed = ", ".join(name for name, ok in row["checks"].items() if not ok) or "-"
        lines.append(
            f"| {row['id']} | {row['truth_system']} | {row['extracted_system']} "
            f"| {row['s1_answer']} | {missed} |"
        )
    lines += [
        "",
        f"## Held-out set: {len(sim_rows)} scripted sim callers vs hidden persona",
        "",
        "Not used to tune the keyword lists.",
        "",
    ]
    lines += _summary(sim_rows, "Sim callers:")
    lines += [
        "",
        "| Caller | True needs | Extracted needs | True route | Extracted route | System 1 answer |",
        "|---|---|---|---|---|---|",
    ]
    for row in sim_rows:
        lines.append(
            f"| {row['id']} | {row['true_needs']} | {row['got_needs']} | {row['truth_system']} "
            f"| {row['extracted_system']} | {row['s1_answer']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    fixture_rows = [score_fixture(fixture_id) for fixture_id in all_ids()]
    sim_rows = [score_sim(spec) for spec in CATALOG]
    text = report(fixture_rows, sim_rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
