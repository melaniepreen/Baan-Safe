"""Hidden caller state. Synthetic households only. The agent does not receive this."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HiddenPersona:
    caller_id: str
    true_needs: tuple[str, ...]
    true_urgency: str
    location: str
    vulnerable: tuple[str, ...]
    household_id: str


@dataclass(frozen=True)
class CallerSpec:
    """One trait combination. `pattern` links siblings for the held-out split."""

    combo_id: str
    traits: tuple[str, ...]
    pattern: str | None
    critical: bool
    persona: HiddenPersona


@dataclass(frozen=True)
class CallerTurn:
    index: int
    public_text: str
    private_trace: str
