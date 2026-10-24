"""Overlay signatures, persistence, and the learned S1 rule / demotion."""

from contracts.models import Need
from eval.rl.themes import THEMES, variant_case
from gateway.chooser import choose
from gateway.overlay import (
    Overlay,
    coarse_signature,
    load,
    load_from_env,
    narrow_signature,
    save,
)
from system1.decide import decide
from system1.extract import extract


def _extracted(theme_id, index=0):
    theme = next(item for item in THEMES if item.theme_id == theme_id)
    case = variant_case(theme, theme.variants[index])
    fields, flags = extract(case.transcript)
    case.fields = fields
    case.policy_flags = ["keyword_extraction", *flags]
    return case


def test_signatures_stable_across_variants():
    one = _extracted("road-info", 0)
    two = _extracted("road-info", 1)
    assert coarse_signature(one) == coarse_signature(two)
    assert narrow_signature(one) == narrow_signature(two)
    other = _extracted("cold-hall", 0)
    assert narrow_signature(other) != narrow_signature(one)


def test_enrichment_flags_are_excluded():
    case = _extracted("rice")
    case.policy_flags = [
        "keyword_extraction",
        "in_active_flood_extent",
        "heavy_rain_forecast",
    ]
    assert "flags=none" in coarse_signature(case)


def test_round_trip(tmp_path):
    overlay = Overlay(
        graduation_threshold=2,
        graduated={"sig|text=abc": {"priority": "P4"}},
        recommendations={"sig|text=def": {"priority": "P2", "count": 1}},
        demoted={"sig": {"reason": "under", "since": "now"}},
    )
    path = tmp_path / "overlay.json"
    save(overlay, path)
    loaded = load(path)
    assert loaded == overlay
    assert loaded.to_dict()["schema"] == "baansafe.rl_overlay.v1"


def test_rl_overlay_env_opt_in(tmp_path, monkeypatch):
    overlay = Overlay(demoted={"coarse": {"reason": "x", "since": "y"}})
    path = tmp_path / "overlay.json"
    save(overlay, path)
    monkeypatch.delenv("RL_OVERLAY", raising=False)
    assert load_from_env() is None
    monkeypatch.setenv("RL_OVERLAY", str(path))
    assert load_from_env() == overlay


def test_graduated_rule_fast_routes(tmp_path):
    case = _extracted("road-info")
    narrow = narrow_signature(case)
    overlay = Overlay(
        graduated={
            narrow: {
                "priority": "P4",
                "route": "information_only",
                "needs": ["information"],
                "requires_human": False,
                "wins": 2,
                "since": "now",
            }
        }
    )
    outcome = decide(case, overlay=overlay)
    assert outcome.outcome == "fast_route"
    assert outcome.route.value == "information_only"
    assert outcome.priority.value == "P4"
    assert outcome.needs == [Need.information]
    assert "Graduated pattern" in outcome.reason


def test_demoted_signature_escalates_and_triggers():
    case = _extracted("weak-grandfather-water")
    coarse = coarse_signature(case)
    overlay = Overlay(demoted={coarse: {"reason": "under", "since": "now"}})
    outcome = decide(case, overlay=overlay)
    assert outcome.outcome == "escalate"
    assert "demotion" in outcome.reason.lower()
    system, triggers = choose(case, overlay)
    assert system.value == "system_2"
    assert "learned:demoted" in triggers
