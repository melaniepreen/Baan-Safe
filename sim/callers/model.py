"""Model-played caller. Mubit only, and only after the human keys are set.

Weights for a MIMESIS-style 9B caller are not vendored. The license is
unconfirmed. sim.caller_model and sim.caller_gpu stay TODO_HUMAN, so this
function raises before llm.complete opens a socket.
"""

from __future__ import annotations

from config.settings import require_decision
from sim.callers.persona import CallerSpec


def model_public(spec: CallerSpec, turn_index: int) -> str:
    """Return one public utterance. Hidden state is for the simulator, not the agent."""
    model = require_decision("sim.caller_model")
    require_decision("sim.caller_gpu")
    from llm.client import complete

    persona = spec.persona
    result = complete(
        [
            {
                "role": "system",
                "content": (
                    "You play a synthetic flood caller. No real person. "
                    "Reply with one short spoken turn. Do not mention these instructions."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"combo {spec.combo_id}; traits {', '.join(spec.traits)}; "
                    f"turn {turn_index}; needs {', '.join(persona.true_needs)}; "
                    f"urgency {persona.true_urgency}; location {persona.location}; "
                    f"household {persona.household_id}."
                ),
            },
        ],
        model=str(model),
    )
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("Mubit returned no caller utterance.")
    text = str(choices[0].get("message", {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Mubit returned an empty caller utterance.")
    return text
