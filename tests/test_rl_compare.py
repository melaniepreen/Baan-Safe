"""`eval.rl.compare`: two RL snapshots side by side. Pure, no network.

Two tiny run dicts cover the pairing and deltas; the committed snapshots
cover the listing. `load_snapshot` must reject anything that is not a bare,
listed folder name because `GET /training/compare` passes query strings in.
"""

from __future__ import annotations

import json

import pytest

from eval.rl import compare as module
from eval.rl.compare import (
    SNAPSHOT_ROOT,
    compare,
    headline_line,
    list_snapshots,
    load_snapshot,
    main,
    render_markdown,
)

COMMITTED = ["20261025T0407Z-memory-empty", "20261025T0600Z-memory-local"]


def _epoch(epoch, **values):
    base = {
        "epoch": epoch,
        "episodes": 4,
        "correct": 2,
        "under_triage": 1,
        "critical_under": 1,
        "missed_human": 0,
        "mean_reward": 0.0,
        "s2_fallbacks": 0,
        "share_s1_only": 0.25,
        "share_cascade": 0.25,
        "share_s2_only": 0.5,
    }
    base.update(values)
    return base


def _run(epochs, *, graduated=None, recommendations=None, demoted=None, live_ok=5):
    return {
        "schema": "baansafe.rl_run.v1",
        "model": "nvidia/nemotron-3-nano-30b-a3b",
        "seed": 17,
        "s2": "fake",
        "epochs": epochs,
        "final_overlay": {
            "schema": "baansafe.rl_overlay.v1",
            "graduation_threshold": 2,
            "graduated": graduated or {},
            "recommendations": recommendations or {},
            "demoted": demoted or [],
        },
        "mubit": {
            "live_ok": live_ok,
            "cache_hits": 1,
            "errors": 0,
            "mubit_chat_count": live_ok + 1,
            "avg_latency_ms": 100.5,
            "model": "nvidia/nemotron-3-nano-30b-a3b",
            "via": "gateway",
        },
    }


@pytest.fixture
def pair():
    a = _run(
        [
            _epoch(1, correct=1, critical_under=3, mean_reward=-0.5, under_triage=3, missed_human=2),
            _epoch(2, correct=2, critical_under=3, mean_reward=-0.4, under_triage=3, missed_human=2),
        ],
        graduated={"sig-a": {}},
        demoted=["sig-d"],
    )
    b = _run(
        [
            _epoch(1, correct=3, critical_under=1, mean_reward=-0.1, under_triage=1, missed_human=1),
            _epoch(2, correct=4, critical_under=0, mean_reward=0.2, under_triage=1, missed_human=0),
        ],
        recommendations={"sig-r1": {}, "sig-r2": {}},
        live_ok=9,
    )
    return a, b


def test_compare_headline_is_last_epoch_with_b_minus_a_delta(pair):
    a, b = pair
    result = compare(a, b, "left", "right")
    assert result["schema"] == "baansafe.rl_compare.v1"
    assert result["a"]["name"] == "left" and result["b"]["name"] == "right"
    assert result["headline"]["critical_under"] == {"a": 3, "b": 0, "delta": -3}
    assert result["headline"]["mean_reward"] == {"a": -0.4, "b": 0.2, "delta": pytest.approx(0.6)}
    assert result["headline"]["correct"] == {"a": 2, "b": 4, "delta": 2}
    assert result["headline"]["under_triage"] == {"a": 3, "b": 1, "delta": -2}
    assert result["headline"]["missed_human"] == {"a": 2, "b": 0, "delta": -2}
    # Integer metrics stay integers; the float delta is rounded to 3 places.
    assert isinstance(result["headline"]["correct"]["delta"], int)
    assert result["headline"]["mean_reward"]["delta"] == 0.6


def test_compare_pairs_epochs_by_number_and_counts_overlay(pair):
    a, b = pair
    result = compare(a, b, "left", "right")
    assert [row["epoch"] for row in result["per_epoch"]] == [1, 2]
    first = result["per_epoch"][0]
    assert first["a"]["correct"] == 1 and first["b"]["correct"] == 3
    assert first["delta"]["correct"] == 2
    assert first["delta"]["critical_under"] == -2
    assert first["delta"]["mean_reward"] == pytest.approx(0.4)
    assert result["a"]["overlay"] == {"graduated": 1, "recommendations": 0, "demoted": 1}
    assert result["b"]["overlay"] == {"graduated": 0, "recommendations": 2, "demoted": 0}
    assert result["a"]["mubit"]["live_ok"] == 5 and result["b"]["mubit"]["live_ok"] == 9
    assert result["a"]["model"] == "nvidia/nemotron-3-nano-30b-a3b"
    assert result["a"]["seed"] == 17 and result["a"]["s2"] == "fake"
    assert set(result["a"]["epochs"][0]) == {
        "epoch",
        "episodes",
        "mean_reward",
        "correct",
        "under_triage",
        "critical_under",
        "missed_human",
        "share_s1_only",
        "share_cascade",
        "share_s2_only",
        "s2_fallbacks",
    }


def test_compare_missing_epoch_on_one_side_is_none(pair):
    a, b = pair
    b_short = {**b, "epochs": b["epochs"][:1]}
    result = compare(a, b_short, "left", "right")
    assert [row["epoch"] for row in result["per_epoch"]] == [1, 2]
    second = result["per_epoch"][1]
    assert second["a"]["correct"] == 2
    assert second["b"] is None
    assert second["delta"] == {metric: None for metric in second["delta"]}
    # Headline still compares the last epoch each side has.
    assert result["headline"]["critical_under"] == {"a": 3, "b": 1, "delta": -2}

    empty = compare(a, {**b, "epochs": []}, "left", "right")
    assert empty["headline"]["critical_under"] == {"a": 3, "b": None, "delta": None}
    assert empty["b"]["epochs"] == []
    assert empty["b"]["overlay"] == {"graduated": 0, "recommendations": 2, "demoted": 0}


def test_compare_tolerates_a_bare_run():
    result = compare({}, {"epochs": "not a list", "final_overlay": None}, "x", "y")
    assert result["headline"]["mean_reward"] == {"a": None, "b": None, "delta": None}
    assert result["per_epoch"] == []
    assert result["a"]["overlay"] == {"graduated": 0, "recommendations": 0, "demoted": 0}
    assert result["b"]["mubit"]["live_ok"] is None


def test_render_markdown_names_both_sides_and_the_delta(pair):
    a, b = pair
    result = compare(a, b, "left-run", "right-run")
    text = render_markdown(result)
    assert text.startswith("# RL snapshot comparison")
    assert "`left-run`" in text and "`right-run`" in text
    assert "| critical_under | 3 | 0 | -3 |" in text
    assert "| mean_reward | -0.4 | 0.2 | +0.6 |" in text
    assert "| correct | 2 | 4 | +2 |" in text
    assert "## Per epoch" in text and "## Mubit" in text and "## Overlay" in text
    assert "| graduated | 1 | 0 |" in text
    assert "| recommendations | 0 | 2 |" in text
    assert "| live_ok | 5 | 9 |" in text
    assert "| 1 | 1 | 3 | +2 |" in text  # epoch 1: correct A, B, delta
    line = headline_line(result)
    assert line.startswith("left-run vs right-run: critical_under 3 -> 0 (-3)")
    assert "mean_reward -0.4 -> 0.2 (+0.6)" in line
    assert "correct 2 -> 4 (+2)" in line


def test_render_markdown_with_no_epochs_does_not_raise():
    text = render_markdown(compare({}, {}, "a", "b"))
    assert "| critical_under | — | — | — |" in text
    assert "## Per epoch" in text


def test_list_snapshots_returns_the_committed_runs_in_order():
    assert SNAPSHOT_ROOT.is_dir()
    assert list_snapshots() == COMMITTED


def test_load_snapshot_rejects_paths_and_unknown_names(tmp_path):
    for bad in ("../x", "..", "a/b", "a\\b", "", "nope", "20261025T0407Z-memory-empty/"):
        with pytest.raises(ValueError):
            load_snapshot(bad)
    # The folder exists but is not listed because run.json is absent.
    (tmp_path / "no-run").mkdir()
    (tmp_path / "with-run").mkdir()
    (tmp_path / "with-run" / "run.json").write_text(json.dumps({"epochs": []}), encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert list_snapshots(tmp_path) == ["with-run"]
    with pytest.raises(ValueError):
        load_snapshot("no-run", tmp_path)
    assert load_snapshot("with-run", tmp_path) == {"epochs": []}
    assert list_snapshots(tmp_path / "absent") == []


def test_load_snapshot_reads_the_committed_run():
    run = load_snapshot(COMMITTED[0])
    assert run["schema"] == "baansafe.rl_run.v1"
    assert run["epochs"][-1]["critical_under"] == 9
    assert load_snapshot(COMMITTED[1])["epochs"][-1]["critical_under"] == 2


def test_main_writes_markdown_and_json_and_prints_the_headline(tmp_path, capsys):
    assert main(["--out-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"{COMMITTED[0]} vs {COMMITTED[1]}: critical_under 9 -> 2 (-7)")
    markdown = (tmp_path / "rl_compare.md").read_text(encoding="utf-8")
    assert "| critical_under | 9 | 2 | -7 |" in markdown
    payload = json.loads((tmp_path / "rl_compare.json").read_text(encoding="utf-8"))
    assert payload["a"]["name"] == COMMITTED[0]
    assert payload["b"]["name"] == COMMITTED[1]
    assert payload["headline"]["mean_reward"]["b"] == 0.189

    # Swapped sides, explicit names.
    assert main(["--a", COMMITTED[1], "--b", COMMITTED[0], "--out-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith(f"{COMMITTED[1]} vs {COMMITTED[0]}: critical_under 2 -> 9 (+7)")

    assert main(["--a", "../etc", "--out-dir", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "available:" in err and COMMITTED[0] in err


def test_main_without_snapshots_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(module, "SNAPSHOT_ROOT", tmp_path / "none")
    assert main(["--out-dir", str(tmp_path)]) == 2
    assert "make rl-snapshot" in capsys.readouterr().err
    assert not (tmp_path / "rl_compare.md").exists()
