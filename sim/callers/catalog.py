"""Fixed synthetic callers. Trait combinations are the held-out unit."""

from __future__ import annotations

from sim.callers.persona import CallerSpec, HiddenPersona
from sim.callers.traits import TRAIT_IDS


def _spec(
    combo_id: str,
    traits: tuple[str, ...],
    pattern: str | None,
    urgency: str,
    critical: bool,
    location: str,
    needs: tuple[str, ...],
    vulnerable: tuple[str, ...] = ("infant",),
) -> CallerSpec:
    unknown = [trait for trait in traits if trait not in TRAIT_IDS]
    if unknown:
        raise ValueError(f"unknown traits on {combo_id}: {unknown}")
    return CallerSpec(
        combo_id=combo_id,
        traits=traits,
        pattern=pattern,
        critical=critical,
        persona=HiddenPersona(
            caller_id=f"synthetic:{combo_id}",
            true_needs=needs,
            true_urgency=urgency,
            location=location,
            vulnerable=vulnerable,
            household_id=f"synthetic:household:{combo_id}",
        ),
    )


# Two combinations share a pattern so a correction on one can change the
# stub score of the other. A combination with pattern None cannot.
CATALOG: tuple[CallerSpec, ...] = (
    _spec(
        "sim-under-lampang",
        ("under_reports", "panicked_fragmented"),
        "under_reports",
        "P1",
        True,
        "Mueang Lampang District",
        ("rescue",),
    ),
    _spec(
        "sim-under-nan",
        ("under_reports", "proxy"),
        "under_reports",
        "P1",
        True,
        "Mueang Nan District",
        ("rescue",),
    ),
    _spec(
        "sim-omit-phrae",
        ("omits_location", "poor_line"),
        "omits_location",
        "P1",
        True,
        "Mueang Phrae District",
        ("rescue",),
    ),
    _spec(
        "sim-omit-phayao",
        ("omits_location", "distrusts_authorities"),
        "omits_location",
        "P2",
        False,
        "Mueang Phayao District",
        ("shelter",),
    ),
    _spec(
        "sim-clear-lampang",
        ("needs_repeating",),
        None,
        "P3",
        False,
        "Mueang Lampang District",
        ("water",),
    ),
    _spec(
        "sim-switch-nan",
        ("code_switches", "elderly_hearing"),
        None,
        "P2",
        False,
        "Mueang Nan District",
        ("shelter",),
        ("infant", "older household member"),
    ),
    _spec(
        "sim-over-phrae",
        ("over_reports", "contradicts"),
        None,
        "P3",
        False,
        "Mueang Phrae District",
        ("water",),
    ),
)
