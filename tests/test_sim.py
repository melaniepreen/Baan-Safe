"""Smoke test for the stub caller simulator, coach, and held-out traits."""

from __future__ import annotations

import json
import re

import pytest

from config.settings import DecisionRequired, require_decision
from eval.learning.simulators import (
    predict_priority,
    public_priority,
    render_trait_section,
    summarize,
    trait_under_triage,
)
from eval.learning.simulators import TraitRow
from sim.callers import CATALOG, TRAIT_IDS, URGENCY_CUE, revelation_turns, speak
from sim.callers.catalog import _spec
from sim.coach import rows_for, write_jsonl
from sim.env import run_episode
from training.log import read_events


def _spec_by(combo_id: str):
    return next(spec for spec in CATALOG if spec.combo_id == combo_id)


def test_traits_cover_the_catalog():
    used = {trait for spec in CATALOG for trait in spec.traits}
    assert used == set(TRAIT_IDS)
    ids = [spec.combo_id for spec in CATALOG]
    assert len(ids) == len(set(ids))


def test_scripted_turn_keeps_the_private_trace_off_the_public_text():
    omit = _spec_by("sim-omit-phrae")
    under = _spec_by("sim-under-lampang")
    for index in range(4):
        spoken = speak(omit, index)
        assert spoken.private_trace not in spoken.public_text
        assert omit.persona.location not in spoken.public_text
        assert "Hidden location" not in spoken.public_text
        under_turn = speak(under, index)
        assert under.persona.true_urgency not in under_turn.public_text
        assert URGENCY_CUE["P1"] not in under_turn.public_text.lower()
        assert under.persona.location in under_turn.public_text
    location_at, urgency_at = revelation_turns(omit)
    assert location_at is None
    assert urgency_at == 0
    location_at, urgency_at = revelation_turns(under)
    assert location_at == 0
    assert urgency_at is None


def test_model_backend_stops_before_the_client(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("llm.complete was called")

    monkeypatch.setattr("llm.client.complete", boom)
    with pytest.raises(DecisionRequired, match="sim.caller_model"):
        speak(_spec_by("sim-clear-lampang"), 0, backend="model")
    with pytest.raises(DecisionRequired, match="sim.caller_model"):
        require_decision("sim.caller_model")


def test_episode_hides_truth_from_the_gateway(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("live stage was called")

    monkeypatch.setattr("system1.decide.decide", boom)
    monkeypatch.setattr("system2.decide.decide", boom)
    monkeypatch.setattr("system2.sapling_client.verify", boom)
    episode = run_episode(_spec_by("sim-omit-phayao"), turns=4)
    hidden = episode.hidden()
    assert hidden["vulnerable"] == ("infant",)
    assert hidden["household_id"].startswith("synthetic:")
    for turn in episode.turns:
        assert turn.pipeline["gateway"] == "called"
        assert turn.pipeline["blocked_on"] is None
        assert turn.pipeline["system"] in {"system_1", "system_2"}
        assert turn.pipeline["sapling"] == "not_called"
        assert turn.pipeline["merge"] == "called"
        blob = "\n".join(turn.agent_texts)
        assert turn.caller.private_trace not in blob
        assert episode.spec.persona.location not in blob
        assert "infant" not in turn.operator_text
    notes = {row["note"] for row in rows_for(episode)}
    assert "asked for location too late" in notes
    assert "missed a vulnerable household member" in notes


def test_coach_jsonl_stays_unpromoted(tmp_path):
    episode = run_episode(_spec_by("sim-under-nan"), turns=4)
    path = tmp_path / "coach.jsonl"
    count = write_jsonl([episode], path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert count == len(rows) >= 2
    assert {row["source"] for row in rows} == {"coach"}
    assert {row["promoted"] for row in rows} == {False}
    assert all("corrected_by" not in row for row in rows)
    blob = path.read_text(encoding="utf-8")
    assert re.search(r"\b\d{13}\b", blob) is None
    assert "accepted an under-reported severity" in blob
    events = read_events()
    assert {event.source for event in events} == {"coach", "sim"}
    assert all(event.schema_version == 1 for event in events)
    assert all(event.group_id == "sim-under-nan" for event in events)
    assert all(event.corrected_by is None for event in events)
    assert all(event.input_ref.case_id == "SIM-sim-under-nan" for event in events)
    sim_rows = [event for event in events if event.source == "sim"]
    coach_rows = [event for event in events if event.source == "coach"]
    assert len(sim_rows) == 1
    assert sim_rows[0].weight == 0.25
    assert sim_rows[0].output_correct.value == "flood_trapped"
    assert {event.weight for event in coach_rows} == {0.5}
    assert all(event.output_correct.value not in {"P1", "P2", "P3", "P4"} for event in events)
    joined = " ".join(event.reason for event in events)
    assert episode.turns[0].caller.private_trace not in joined


def test_held_out_trait_arms_transfer_a_sibling_pattern():
    held = _spec_by("sim-under-nan")
    sibling = _spec_by("sim-under-lampang")
    other = _spec_by("sim-clear-lampang")
    assert public_priority(held) == "P4"
    assert predict_priority("A", held, [sibling]) == "P4"
    assert predict_priority("shuffled", held, [sibling]) == "P4"
    assert predict_priority("B", held, [sibling]) == "P1"
    assert predict_priority("C", held, [sibling]) == "P1"
    assert predict_priority("C", held, [other]) == "P4"
    omit = _spec_by("sim-omit-phrae")
    rows = [
        TraitRow(held.combo_id, held.traits, True, "P1", "P4"),
        TraitRow(omit.combo_id, omit.traits, True, "P1", "P4"),
        TraitRow(other.combo_id, other.traits, False, "P3", "P3"),
    ]
    assert trait_under_triage(rows, "under_reports") == 1
    assert trait_under_triage(rows, "omits_location") == 1
    assert trait_under_triage([], "under_reports") is None
    for seed in summarize():
        assert seed["arms"]["shuffled"] == seed["arms"]["A"]
        assert set(seed["correction"]).isdisjoint(seed["held_out"])
    text = render_trait_section()
    assert "under_reports" in text
    assert "omits_location" in text
    assert "unseen user simulator" in text
    assert "2610.09484" in text
    assert "TODO_HUMAN" in text


def test_catalog_rejects_an_unknown_trait():
    with pytest.raises(ValueError):
        _spec("sim-bad", ("not-a-trait",), None, "P4", False, "Mueang Nan District", ("information",))
