"""RL loop with a fake System 2: graduation, recommendation, demotion."""

import json

from contracts.models import System
from eval.rl.learner import Learner
from eval.rl.run import run
from eval.rl.themes import THEMES, variant_case
from gateway.overlay import coarse_signature, narrow_signature
from system1.extract import extract


def _narrow(theme_id, index=0):
    theme = next(item for item in THEMES if item.theme_id == theme_id)
    case = variant_case(theme, theme.variants[index])
    fields, flags = extract(case.transcript)
    case.fields = fields
    case.policy_flags = ["keyword_extraction", *flags]
    return narrow_signature(case)


def _coarse(theme_id):
    theme = next(item for item in THEMES if item.theme_id == theme_id)
    case = variant_case(theme, theme.variants[0])
    fields, flags = extract(case.transcript)
    case.fields = fields
    case.policy_flags = ["keyword_extraction", *flags]
    return coarse_signature(case)


def test_fake_loop_learns(tmp_path):
    payload = run(s2="fake", epochs=2, out_dir=tmp_path / "rl")
    overlay = payload["final_overlay"]

    for theme_id in ("road-info", "cold-hall"):
        assert _narrow(theme_id) in overlay["graduated"]
    for theme_id in ("quiet-grandmother", "upstairs-water"):
        narrow = _narrow(theme_id)
        assert narrow in overlay["recommendations"]
        assert narrow not in overlay["graduated"]
    for theme_id in ("aid-list", "fine-but-door"):
        assert _narrow(theme_id) not in overlay["graduated"]
        assert _narrow(theme_id) not in overlay["recommendations"]
    assert _coarse("weak-grandfather-water") in overlay["demoted"]

    kinds = [event["kind"] for event in payload["events"]]
    assert sorted(kinds) == ["demote", "graduate", "graduate", "recommend", "recommend"]
    assert len(kinds) == len(set(
        (event["kind"], event["signature"]) for event in payload["events"]
    ))

    weak = [
        row
        for row in payload["episodes"]
        if row["id"].startswith("RL-WEAK") and row["epoch"] == 2
    ]
    assert weak and all(row["systems"] == ["system_2"] for row in weak)
    assert all(row["correct"] for row in weak)

    graduated_road = [
        row
        for row in payload["episodes"]
        if row["id"] == "RL-ROAD-3" and row["epoch"] >= 1
    ]
    assert any(row["systems"] == ["system_1"] and row["correct"] for row in graduated_road)

    assert payload["schema"] == "baansafe.rl_run.v1"
    for key in ("epochs", "episodes", "events", "final_overlay", "training", "notes"):
        assert key in payload
    on_disk = json.loads((tmp_path / "rl" / "run.json").read_text())
    assert on_disk["schema"] == "baansafe.rl_run.v1"


def test_bandit_allowed_arms():
    learner = Learner()
    door = variant_case(
        next(t for t in THEMES if t.theme_id == "fine-but-door"),
        THEMES[7].variants[0],
    )
    road = variant_case(
        next(t for t in THEMES if t.theme_id == "road-info"),
        THEMES[0].variants[0],
    )
    # Hard trigger fired: only the system_2 arm is allowed.
    learner._bandit(
        door, "coarse-a", {System.system_2},
        hard_triggers=["need:rescue"], reward=1.0, epoch=1, sequence=0,
    )
    assert learner.bandit_log[-1]["pick"] == "system_2"
    # No hard trigger: either arm may be picked, and both arms get updated.
    learner._bandit(
        road, "coarse-b", {System.system_1, System.system_2},
        hard_triggers=[], reward=-1.0, epoch=1, sequence=1,
    )
    entry = learner.bandit_log[-1]
    assert entry["pick"] in {"system_1", "system_2"}
    assert ("coarse-b", "system_1") in learner.bandit
    assert ("coarse-b", "system_2") in learner.bandit
