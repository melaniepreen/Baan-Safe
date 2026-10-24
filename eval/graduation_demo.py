"""Correction graduation demo. `make demo-graduation`.

Two human s1_triage corrections on two distinct cases with the same pattern
graduate it: F02 then routes to System 2 tagged `complex_situation`, with a
recommendation in memory. A temp TRAINING_EVENTS_PATH keeps the real log
untouched (restored afterwards, as eval/correction_loop.py does).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from api.store import StoredCase, put, reset
from contracts.training import (
    LEGACY_MODEL_VERSION,
    InputRef,
    S1Label,
    TrainingEvent,
    current_policy_version,
)
from fixtures.load import load_case
from gateway.route import handle
from training.log import append_event


def _restore(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


def _event(case_id: str) -> TrainingEvent:
    return TrainingEvent(
        task="s1_triage",
        group_id=case_id,
        input_ref=InputRef(case_id=case_id, lang="en"),
        output_model=S1Label.sphere_food_short,
        output_correct=S1Label.safeguarding_child,
        reason=(
            "Operator correction: a child in the household is a safeguarding "
            "pattern, not a routine food request."
        ),
        source="human",
        corrected_by="operator",
        model_version=LEGACY_MODEL_VERSION,
        policy_version=current_policy_version(),
    )


def _line(decision, case) -> str:
    source = decision.source_outcomes[0]
    return (
        f"system={source.system.value} next_action={decision.next_action.value} "
        f"priority={decision.final_priority.value} flags={case.policy_flags}"
    )


def main() -> int:
    previous = os.environ.get("TRAINING_EVENTS_PATH")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TRAINING_EVENTS_PATH"] = str(Path(tmp) / "events.jsonl")
        reset()
        try:
            before = load_case("F02")
            decision = handle(before, use_stubs=True)
            print("F02 before:", _line(decision, before))

            twin = before.model_copy(update={"case_id": "DEMO-F02-b"})
            put(StoredCase(state=twin, fixture_id=None))

            for case_id in ("F02", "DEMO-F02-b"):
                append_event(_event(case_id))
            print("appended 2 human s1_triage corrections "
                  "(safeguarding_child) on F02 and DEMO-F02-b")

            after = load_case("F02")
            decision = handle(after, use_stubs=True)
            print("F02 after: ", _line(decision, after))
            graduated = [
                item
                for item in after.memory_context
                if item.memory_id.startswith("graduated-")
            ]
            print("memory:", [item.summary for item in graduated])
            assert "complex_situation" in after.policy_flags
            assert decision.source_outcomes[0].system.value == "system_2"
            assert decision.source_outcomes[0].priority.value == "P2"
            print(
                "graduation sets no priority: the P2 here is the fallback "
                "escalation, not a graduated rule"
            )
            print(
                "no F02 s2 stub exists, so the fallback escalation to a "
                "supervisor is the expected, honest outcome"
            )
            print("nothing was promoted into System 1")
        finally:
            reset()
            _restore("TRAINING_EVENTS_PATH", previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
