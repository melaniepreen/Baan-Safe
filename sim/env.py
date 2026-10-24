"""Multi-turn environment. A scripted caller, then the gateway path.

The live chooser is gateway.route_chooser and is TODO_HUMAN, so a synthetic
case id stops in the gateway. This module does not pick System 1 and System 2,
does not call Sapling, and does not call router.merge. The operator lines are
a stub and do not read the hidden persona or the private trace.

Sapling, when a human wires it, sits inside system2.decide after the
orchestrator and before the Decision Router. The stub gateway does not enter
that function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from config.settings import DecisionRequired
from contracts.models import CaseState, ExtractedFields, TranscriptTurn
from sim.callers import N_TURNS, CallerSpec, speak
from sim.callers.persona import CallerTurn

# The stub operator waits until turn 2 to ask for a district. The coach
# treats that as late. These lines are fixed so they cannot leak hidden state.
OPERATOR_LINES: tuple[str, ...] = (
    "Please say that again.",
    "How many people are in the house?",
    "Which district is the house in?",
    "A person will review this call.",
)

RECEIVED_AT = datetime(2026, 10, 6, tzinfo=timezone.utc)


@dataclass(frozen=True)
class TurnLog:
    index: int
    caller: CallerTurn
    operator_text: str
    pipeline: dict
    agent_texts: tuple[str, ...]


@dataclass(frozen=True)
class Episode:
    spec: CallerSpec
    turns: tuple[TurnLog, ...]

    def hidden(self) -> dict:
        persona = self.spec.persona
        return {
            "caller_id": persona.caller_id,
            "true_needs": persona.true_needs,
            "true_urgency": persona.true_urgency,
            "location": persona.location,
            "vulnerable": persona.vulnerable,
            "household_id": persona.household_id,
            "private_traces": tuple(turn.caller.private_trace for turn in self.turns),
        }


def run_episode(spec: CallerSpec, turns: int = N_TURNS, backend: str = "scripted") -> Episode:
    """Play `turns` of caller, gateway, and stub operator. Logs hidden truth aside."""
    if turns > len(OPERATOR_LINES):
        raise ValueError(f"stub operator has {len(OPERATOR_LINES)} lines")
    transcript: list[TranscriptTurn] = []
    logs: list[TurnLog] = []
    for index in range(turns):
        spoken = speak(spec, index, backend=backend)
        transcript.append(
            TranscriptTurn(t_ms=index * 2000, speaker="caller", text=spoken.public_text)
        )
        case = _case(spec, transcript)
        pipeline = _drive(case)
        reply = OPERATOR_LINES[index]
        transcript.append(
            TranscriptTurn(t_ms=index * 2000 + 1000, speaker="operator", text=reply)
        )
        logs.append(
            TurnLog(
                index=index,
                caller=spoken,
                operator_text=reply,
                pipeline=pipeline,
                agent_texts=tuple(turn.text for turn in transcript),
            )
        )
    return Episode(spec=spec, turns=tuple(logs))


def _case(spec: CallerSpec, transcript: list[TranscriptTurn]) -> CaseState:
    """Case the gateway sees. Fields stay empty: hidden truth is not extracted."""
    return CaseState(
        case_id=f"SIM-{spec.combo_id}",
        caller_id_hash=spec.persona.caller_id,
        transcript=list(transcript),
        fields=ExtractedFields(),
        received_at=RECEIVED_AT,
    )


def _drive(case: CaseState) -> dict:
    """Call the gateway once. Record the stages that did not run."""
    from gateway.route import handle

    try:
        decision = handle(case, use_stubs=True)
    except DecisionRequired:
        return {
            "gateway": "called",
            "blocked_on": "gateway.route_chooser",
            "system": "not_selected",
            "sapling": "not_called",
            "decision_router": "not_called",
            "merge": "not_called",
        }
    system = decision.source_outcomes[0].system.value
    return {
        "gateway": "called",
        "blocked_on": None,
        "system": system,
        "sapling": "not_called_on_stub_gateway",
        "decision_router": "stub_copy",
        "merge": "not_called",
        "next_action": decision.next_action.value,
        "priority": decision.final_priority.value,
    }
