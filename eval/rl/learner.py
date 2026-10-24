"""Post-episode learning: graduation, demotion, and the shadow bandit.

The bandit never routes. It is a shadow scorer over (coarse signature,
system) arms. Narrow signatures promote; coarse signatures demote.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from contracts.models import CaseState, Need, Outcome, Route, RouterDecision, System
from eval.rl.reward import Score
from eval.rl.themes import Truth
from gateway.chooser import system_2_triggers
from gateway.overlay import Overlay, coarse_signature, narrow_signature

_COMPLEX_ROUTES = {Route.supervisor_escalation, Route.aid_caseworker}
_COMPLEX_FLAGS = {
    "safeguarding",
    "conflicting_evidence",
    "aid_exception",
    "aid_eligibility",
    "aid_denial",
}


@dataclass
class EpisodeContext:
    case: CaseState
    decision: RouterDecision
    truth: Truth
    score: Score


@dataclass
class Learner:
    overlay: Overlay = field(default_factory=Overlay)
    threshold: int = 2
    rng: random.Random = field(default_factory=lambda: random.Random(17))
    streaks: dict[str, tuple[tuple, int]] = field(default_factory=dict)
    bandit: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    bandit_log: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def learn(self, episode: EpisodeContext, epoch: int, sequence: int) -> None:
        case = episode.case
        decision = episode.decision
        ran = {outcome.system for outcome in decision.source_outcomes}
        s2 = next(
            (o for o in decision.source_outcomes if o.system is System.system_2),
            None,
        )
        s2_fell_back = s2 is not None and "system2_unavailable" in s2.missing_evidence
        cascaded = System.system_1 in ran and System.system_2 in ran
        coarse = coarse_signature(case)
        narrow = narrow_signature(case)

        if cascaded and s2 is not None and not s2_fell_back:
            self._graduation(case, s2, episode, coarse, narrow, epoch, sequence)
        elif ran == {System.system_1} and (
            episode.score.under_triage or episode.score.missed_human
        ):
            self._demote(coarse, narrow, episode, epoch, sequence)
        self._bandit(case, coarse, ran, hard_triggers=system_2_triggers(case),
                     reward=episode.score.reward, epoch=epoch, sequence=sequence)

    def _graduation(
        self,
        case: CaseState,
        s2: Outcome,
        episode: EpisodeContext,
        coarse: str,
        narrow: str,
        epoch: int,
        sequence: int,
    ) -> None:
        key = (
            s2.priority.value,
            s2.route.value,
            s2.requires_human,
        )
        last = self.streaks.get(narrow)
        streak = last[1] + 1 if (last and last[0] == key and episode.score.correct) else (
            1 if episode.score.correct else 0
        )
        self.streaks[narrow] = (key, streak)
        if streak < self.threshold or coarse in self.overlay.demoted:
            return
        payload = {
            "priority": s2.priority.value,
            "route": s2.route.value,
            "needs": [need.value for need in s2.needs],
            "requires_human": s2.requires_human,
        }
        if s2.priority.value == "P1" or _is_complex(case, s2):
            entry = self.overlay.recommendations.get(narrow)
            if entry is None:
                self.overlay.recommendations[narrow] = {
                    **payload,
                    "count": 1,
                    "why": "P1 or complex pattern; a human keeps authority.",
                }
                self.events.append(
                    _event("recommend", epoch, sequence, case.case_id, narrow, payload)
                )
            else:
                entry["count"] += 1
            return
        rule = self.overlay.graduated.get(narrow)
        if rule is None:
            self.overlay.graduated[narrow] = {
                **payload,
                "wins": streak,
                "since": _now(),
            }
            self.events.append(
                _event("graduate", epoch, sequence, case.case_id, narrow, payload)
            )
        else:
            rule["wins"] = streak

    def _demote(
        self,
        coarse: str,
        narrow: str,
        episode: EpisodeContext,
        epoch: int,
        sequence: int,
    ) -> None:
        if coarse in self.overlay.demoted:
            return
        self.overlay.demoted[coarse] = {
            "reason": (
                f"System 1 under-triaged {episode.case.case_id}: "
                f"predicted {episode.decision.final_priority.value}, "
                f"truth {episode.truth.priority}."
            ),
            "since": _now(),
        }
        prefix = coarse + "|text="
        self.overlay.graduated = {
            key: value
            for key, value in self.overlay.graduated.items()
            if not key.startswith(prefix)
        }
        self.streaks = {
            key: value
            for key, value in self.streaks.items()
            if not key.startswith(prefix)
        }
        self.events.append(
            _event(
                "demote",
                epoch,
                sequence,
                episode.case.case_id,
                coarse,
                {"priority": episode.decision.final_priority.value},
            )
        )

    def _bandit(
        self,
        case: CaseState,
        coarse: str,
        ran: set[System],
        *,
        hard_triggers: list[str],
        reward: float,
        epoch: int,
        sequence: int,
    ) -> None:
        allowed = {System.system_2} if hard_triggers else {System.system_1, System.system_2}
        for system in ran:
            arm = self.bandit.setdefault((coarse, system.value), [1.0, 1.0])
            if reward >= 0.5:
                arm[0] += 1
            else:
                arm[1] += 1
        picks = {
            system.value: self.rng.betavariate(*self.bandit.get((coarse, system.value), [1.0, 1.0]))
            for system in allowed
        }
        pick = max(picks, key=picks.get)
        self.bandit_log.append(
            {
                "epoch": epoch,
                "seq": sequence,
                "case_id": case.case_id,
                "coarse": coarse,
                "pick": pick,
                "actual": sorted(system.value for system in ran),
                "agree": pick in {system.value for system in ran},
            }
        )


def _is_complex(case: CaseState, s2: Outcome) -> bool:
    return (
        s2.requires_human
        or s2.route in _COMPLEX_ROUTES
        or Need.aid_payment in s2.needs
        or bool(set(case.policy_flags) & _COMPLEX_FLAGS)
    )


def _event(
    kind: str,
    epoch: int,
    sequence: int,
    case_id: str,
    signature: str,
    payload: dict,
) -> dict:
    return {
        "kind": kind,
        "epoch": epoch,
        "seq": sequence,
        "case_id": case_id,
        "signature": signature,
        **payload,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
