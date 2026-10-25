"""Validate fixtures, mocks, decisions, and the do-not-collect boundary."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from config.settings import iter_decision_leaves
from contracts.models import (
    CaseState,
    MemoryItem,
    Need,
    Outcome,
    Priority,
    Route,
    System,
)
from ingest import store
from mocks.loader import ResourcesSnapshot
from paths import ROOT

FIXTURES = ROOT / "fixtures"
MOCKS = ROOT / "mocks"
ERRORS: list[str] = []

PHONE = re.compile(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}")
NATIONAL_ID = re.compile(r"\b\d{13}\b")
BANNED_WORDS = ("promptpay", "passport", "immigration status", "bank account")


def fail(message: str) -> None:
    ERRORS.append(message)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path}: invalid JSON ({exc})")
        return None


def check_text(label: str, text: str) -> None:
    lowered = text.lower()
    if PHONE.search(text):
        fail(f"{label}: looks like a phone number")
    if NATIONAL_ID.search(text):
        fail(f"{label}: looks like a 13-digit id")
    for word in BANNED_WORDS:
        if word in lowered:
            fail(f"{label}: contains '{word}'")


# Humans already made these. Any other leaf stays TODO_HUMAN.
DECIDED = {
    "system2.use_banyan_sapling": True,
    "system2.sapling_scope": "aid_eligibility,denial",
    "sapling.client": "stub",
    "system2.hosting": "openrouter via mubit gateway",
    "llm.provider_route": "mubit",
    "gateway.route_chooser": "field precheck",
    "system1.extraction_method": "rules-only",
    "system2.orchestrator_model": "nvidia/nemotron-3-nano-30b-a3b",
    "system2.max_latency_ms": 10000,
    "correction_loop.graduation_threshold": 2,
    "correction_loop.escalation_threshold": 2,
    "data.demo_event": "Sukhumvit / Watthana (Bangkok)",
    "memory.mubit_project": "baansafe-demo",
    "memory.retrieval_top_k": 5,
    "memory.token_budget": 400,
}


def check_agent_docs() -> None:
    import importlib.util

    path = ROOT / "scripts" / "check_agents.py"
    spec = importlib.util.spec_from_file_location("check_agents", path)
    if spec is None or spec.loader is None:
        fail("scripts/check_agents.py could not be loaded")
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for message in module.check(ROOT):
        fail(message)


def check_decisions() -> None:
    for path, value in iter_decision_leaves():
        if path in DECIDED:
            if value != DECIDED[path]:
                fail(
                    f"config/decisions.yaml:{path} must stay {DECIDED[path]!r}; "
                    f"found {value!r}"
                )
            continue
        if value != "TODO_HUMAN":
            fail(f"config/decisions.yaml:{path} was set to {value!r}; leave it TODO_HUMAN")
    routing = (ROOT / "config" / "routing.yaml").read_text(encoding="utf-8")
    if "mode: exclusive" not in routing and "mode: cascade" not in routing:
        fail("config/routing.yaml mode must be exclusive or cascade")


def check_sapling_stubs() -> None:
    from system2.sapling_client import ACTIONS, CHECKS, VERDICTS

    folder = MOCKS / "sapling_stub"
    paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if len(paths) != 5:
        fail(f"mocks/sapling_stub should hold 5 cases, found {len(paths)}")
    seen: set[str] = set()
    verdicts: set[str] = set()
    checks: set[str] = set()
    for path in paths:
        body = load_json(path)
        if body is None:
            continue
        label = str(path.relative_to(ROOT))
        for key in ("id", "check", "policy", "evidence", "claim", "expected_verdict", "expected_action", "notes"):
            if key not in body:
                fail(f"{label}: missing {key}")
        if body.get("id") in seen:
            fail(f"{label}: duplicate id")
        seen.add(body.get("id"))
        for key in ("policy", "evidence", "claim", "notes"):
            check_text(label, str(body.get(key) or ""))
        verdict = body.get("expected_verdict")
        action = body.get("expected_action")
        check = body.get("check")
        if verdict not in VERDICTS:
            fail(f"{label}: unexpected verdict {verdict!r}")
        elif ACTIONS.get(verdict) != action:
            fail(f"{label}: {verdict} must map to {ACTIONS.get(verdict)}, found {action!r}")
        if check not in CHECKS:
            fail(f"{label}: check {check!r} is outside aid_eligibility,denial")
        verdicts.add(verdict)
        checks.add(check)
    if verdicts != set(VERDICTS):
        fail(f"sapling stubs should cover every verdict, found {sorted(verdicts)}")
    if checks != set(CHECKS):
        fail(f"sapling stubs should cover aid eligibility and denial, found {sorted(checks)}")


def check_stubs_are_stubs() -> None:
    for rel in ("system2/decide.py",):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "NotImplementedError" not in text:
            fail(f"{rel} does not raise NotImplementedError")
        if "Outcome(" in text or "RouterDecision(" in text:
            fail(f"{rel} constructs a decision object")
    gateway = (ROOT / "gateway" / "route.py").read_text(encoding="utf-8")
    if "fields.medical" in gateway or "oxygen_dependent" in gateway:
        fail("gateway/route.py evaluates System 1 escalation rules")


def check_schemas() -> None:
    from contracts.models import MODEL_TYPES

    for model in MODEL_TYPES:
        path = ROOT / "contracts" / "schemas" / f"{model.__name__}.json"
        if not path.exists():
            fail(f"missing schema {path.name}")
    contracts = (ROOT / "contracts" / "CONTRACTS.md").read_text(encoding="utf-8")
    for name in ("case_state.json", "outcome_s1.json", "outcome_s2.json"):
        body = (ROOT / "contracts" / "examples" / name).read_text(encoding="utf-8")
        payload = json.loads(body)
        if name == "case_state.json":
            CaseState.model_validate(payload)
        else:
            Outcome.model_validate(payload)
        if payload["case_id"] if name == "case_state.json" else payload["reason"] not in contracts:
            # The example JSON is embedded in CONTRACTS.md. Compare a stable fragment.
            fragment = payload["case_id"] if name == "case_state.json" else payload["reason"]
            if fragment not in contracts:
                fail(f"CONTRACTS.md is missing example fragment from {name}")


def check_fixture(path: Path, payload: dict, expect_s2: bool) -> None:
    label = str(path.relative_to(ROOT))
    required = {"id", "title", "tags", "transcript_stream", "case_state", "expected", "notes"}
    missing = required - payload.keys()
    if missing:
        fail(f"{label}: missing {sorted(missing)}")
        return
    try:
        CaseState.model_validate(payload["case_state"])
    except Exception as exc:  # noqa: BLE001 — validator collects every file
        fail(f"{label}: case_state {exc}")
    if payload["case_state"]["case_id"] != payload["id"]:
        fail(f"{label}: case_id does not match id")
    if payload["case_state"]["memory_context"]:
        fail(f"{label}: case_state.memory_context must start empty; mocks hold memory")
    caller = payload["case_state"]["caller_id_hash"]
    if not str(caller).startswith("synthetic:"):
        fail(f"{label}: caller_id_hash must start with synthetic:")
    stream = payload["transcript_stream"]
    if not 4 <= len(stream) <= 12:
        fail(f"{label}: transcript has {len(stream)} turns")
    previous = -1
    speakers = set()
    for turn in stream:
        speakers.add(turn.get("speaker"))
        t_ms = turn.get("t_ms", -1)
        if t_ms < previous:
            fail(f"{label}: timestamps go backwards")
        previous = t_ms
        check_text(label, turn.get("text", ""))
    if speakers != {"caller", "operator"}:
        fail(f"{label}: transcript should include caller and operator")
    expected = payload["expected"]
    for key in ("system", "priority", "route", "needs", "requires_human", "missing_evidence", "acceptable_next_questions"):
        if key not in expected:
            fail(f"{label}: expected.{key} missing")
    try:
        System(expected["system"])
        Priority(expected["priority"])
        Route(expected["route"])
        for need in expected["needs"]:
            Need(need)
    except Exception as exc:  # noqa: BLE001
        fail(f"{label}: expected enum {exc}")
    check_text(label, payload.get("notes", ""))
    fid = payload["id"]
    for folder, model in (("memory_context", None), ("s1_stub", Outcome)):
        mock_path = MOCKS / folder / f"{fid}.json"
        if not mock_path.exists():
            fail(f"missing {mock_path.relative_to(ROOT)}")
            continue
        body = load_json(mock_path)
        if body is None:
            continue
        if folder == "memory_context":
            if not isinstance(body, list) or len(body) > 4:
                fail(f"{mock_path.name}: memory must be a list of 0–4 items")
            for item in body or []:
                try:
                    MemoryItem.model_validate(item)
                except Exception as exc:  # noqa: BLE001
                    fail(f"{mock_path.name}: {exc}")
                check_text(str(mock_path), item.get("summary", ""))
        else:
            try:
                Outcome.model_validate(body)
            except Exception as exc:  # noqa: BLE001
                fail(f"{mock_path.name}: {exc}")
    s2_path = MOCKS / "s2_stub" / f"{fid}.json"
    if expect_s2:
        if not s2_path.exists():
            fail(f"missing s2 stub for {fid}")
        else:
            body = load_json(s2_path)
            if body is not None:
                try:
                    outcome = Outcome.model_validate(body)
                except Exception as exc:  # noqa: BLE001
                    fail(f"{s2_path.name}: {exc}")
                else:
                    if outcome.system.value != "system_2":
                        fail(f"{fid}: s2 stub system is not system_2")
                    if outcome.priority.value != expected["priority"]:
                        fail(f"{fid}: s2 priority != expected")
                    if outcome.route.value != expected["route"]:
                        fail(f"{fid}: s2 route != expected")
                    if [need.value for need in outcome.needs] != expected["needs"]:
                        fail(f"{fid}: s2 needs != expected")
                    if outcome.requires_human != expected["requires_human"]:
                        fail(f"{fid}: s2 requires_human != expected")
                    if outcome.missing_evidence != expected["missing_evidence"]:
                        fail(f"{fid}: s2 missing_evidence != expected")
                    if expected["acceptable_next_questions"]:
                        if outcome.next_question not in expected["acceptable_next_questions"]:
                            fail(f"{fid}: next_question not in acceptable list")
    elif s2_path.exists() and "system_2" not in payload["tags"]:
        # Allowed, but graduation stubs are not required.
        pass


def check_pairs(index: dict) -> None:
    pairs = index.get("correction_pairs") or []
    if not pairs:
        fail("fixtures/index.json has no correction_pairs")
    for pair in pairs:
        left, right = pair["a"], pair["b"]
        left_mem = json.loads((MOCKS / "memory_context" / f"{left}.json").read_text(encoding="utf-8"))
        right_mem = json.loads((MOCKS / "memory_context" / f"{right}.json").read_text(encoding="utf-8"))
        if any(item["kind"] == "correction" for item in left_mem):
            fail(f"{left} memory must not contain a correction item")
        if not any(item["kind"] == "correction" and item.get("source_case_id") == left for item in right_mem):
            fail(f"{right} memory must contain a correction sourced from {left}")


def check_data() -> None:
    data_dir = ROOT / "data" / "processed"
    for name in (
        "districts.json",
        "admin_districts.json",
        "weather_observation.json",
        "disaster_report.json",
        "source_status.json",
        "flood.geojson",
        "facilities.geojson",
    ):
        if not (data_dir / name).exists():
            fail(f"data/processed/{name} is missing")
    for row in store.rows("disaster_report"):
        if "body" in row:
            fail("disaster_report has a body key")
        text = row.get("summary") or ""
        if len(text) > 400:
            fail("disaster_report.summary is too long to be a short summary")
        check_text("disaster_report.summary", text)
    for row in store.facilities():
        check_text("infrastructure.name", row.get("name") or "")


def check_counts(payloads: list[dict]) -> None:
    scenarios = [row for row in payloads if "graduation" not in row["tags"]]
    if len(scenarios) != 20:
        fail(f"expected 20 scenarios, found {len(scenarios)}")
    graduation = [row for row in payloads if "graduation" in row["tags"]]
    if len(graduation) != 4:
        fail(f"expected 4 graduation fixtures, found {len(graduation)}")

    def count(tag: str, pool: list[dict] | None = None) -> int:
        rows = scenarios if pool is None else pool
        return sum(1 for row in rows if tag in row["tags"])

    expectations = {
        "clear": 7,
        "duplicate": 2,
        "medical": 2,
        "vague_location": 2,
        "conflicting": 2,
        "safeguarding": 1,
        "aid_exception": 2,
        "correction_pair": 2,
    }
    for tag, expected in expectations.items():
        found = count(tag)
        if found != expected:
            fail(f"tag {tag}: expected {expected}, found {found}")
    if not all("elderly" in row["notes"].lower() or "elderly" in json.dumps(row).lower() for row in graduation):
        fail("graduation set should repeat the elderly pattern")
    priorities = {row["expected"]["priority"] for row in graduation}
    routes = {row["expected"]["route"] for row in graduation}
    if priorities != {"P1"} or routes != {"rescue_coordination"}:
        fail("graduation set should share P1 rescue_coordination")


def main() -> int:
    check_decisions()
    check_sapling_stubs()
    check_stubs_are_stubs()
    check_schemas()
    index = load_json(FIXTURES / "index.json")
    if not index:
        print("\n".join(ERRORS))
        return 1
    payloads = []
    seen = set()
    for group in ("scenarios", "graduation"):
        for entry in index.get(group) or []:
            path = FIXTURES / entry["path"]
            payload = load_json(path)
            if payload is None:
                continue
            seen.add(payload["id"])
            payloads.append(payload)
            expect_s2 = "system_2" in payload.get("tags", [])
            check_fixture(path, payload, expect_s2)
            if entry["id"] != payload["id"]:
                fail(f"index id {entry['id']} != file id {payload['id']}")
    # Every fixture file on disk is listed.
    for path in list((FIXTURES / "scenarios").glob("*.json")) + list((FIXTURES / "graduation").glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        if body["id"] not in seen:
            fail(f"{path.name} is not in fixtures/index.json")
    check_pairs(index)
    resources = load_json(MOCKS / "resources.json")
    if resources is not None:
        try:
            ResourcesSnapshot.model_validate(resources)
        except Exception as exc:  # noqa: BLE001
            fail(f"resources.json: {exc}")
    check_counts(payloads)
    check_data()
    check_agent_docs()
    # Medical policy and vague-location failure are present somewhere.
    medical = False
    prior = False
    for path in (MOCKS / "memory_context").glob("*.json"):
        for item in json.loads(path.read_text(encoding="utf-8")):
            if item["kind"] == "policy" and path.stem in {"F10", "F11"}:
                medical = True
            if item["kind"] == "prior_failure":
                prior = True
    if not medical:
        fail("no policy memory on a medical fixture")
    if not prior:
        fail("no prior_failure memory on a vague-location fixture")
    if ERRORS:
        print(f"{len(ERRORS)} problem(s):")
        for message in ERRORS:
            print(f"- {message}")
        return 1
    print(f"validate ok: {len(payloads)} fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
