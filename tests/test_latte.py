"""Adapter, env mapping, and the skip path. No network and no bun required."""

from __future__ import annotations

import json

import pytest

from eval.latte.env import GatewayEnvError, build_live_env, describe_live_env, map_base
from eval.latte.read import load_reference, load_study
from eval.latte import run
from eval.latte.section import external_section


def test_gateway_root_maps_onto_the_openai_prefix():
    assert map_base("https://api.mubit.ai") == "https://api.mubit.ai/openai/v1"
    assert map_base("https://api.mubit.ai/openai/v1/") == "https://api.mubit.ai/openai/v1"
    assert (
        map_base("https://api.mubit.ai/openai/v1/chat/completions")
        == "https://api.mubit.ai/openai/v1"
    )
    with pytest.raises(GatewayEnvError, match="not a Mubit host"):
        map_base("https://api.openai.com/v1")


def test_live_env_hides_the_key():
    env = build_live_env(
        {
            "MUBIT_BASE_URL": "https://api.mubit.ai",
            "MUBIT_API_KEY": "mbt_should_not_appear",
            "MUBIT_MODEL": "route-a",
            "FRONTIER_MODEL": "route-b",
        }
    )
    text = describe_live_env(env)
    assert "mbt_should_not_appear" not in text
    assert "MUBIT_API_KEY=set" in text
    assert "MUBIT_MODEL=route-a" in text
    assert env["MUBIT_BASE_URL"] == "https://api.mubit.ai/openai/v1"
    with pytest.raises(GatewayEnvError, match="FRONTIER_MODEL"):
        build_live_env(
            {
                "MUBIT_BASE_URL": "https://api.mubit.ai",
                "MUBIT_API_KEY": "mbt_should_not_appear",
                "MUBIT_MODEL": "route-a",
            }
        )


def test_section_reads_results_and_drops_secrets(tmp_path, monkeypatch):
    study_path = tmp_path / "summary.json"
    study_path.write_text(
        json.dumps(
            {
                "identity": {"tag": "example-tag", "commit": "abc123"},
                "groups": [
                    {
                        "model": "example-model",
                        "mode": "no-notes",
                        "complete": True,
                        "passes": 0,
                        "curves": [{"mean": 40.0}],
                        "api_key": "mbt_should_not_appear",
                    },
                    {
                        "model": "example-model",
                        "mode": "notes",
                        "complete": True,
                        "passes": 2,
                        "curves": [{"mean": 55.0}],
                    },
                    {
                        "model": "partial-model",
                        "mode": "notes",
                        "complete": False,
                        "passes": 0,
                        "curves": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    reference = tmp_path / "latte-reference.json"
    reference.write_text(
        json.dumps(
            {
                "mode": "calibrated-reference",
                "task": "heart",
                "seed": 42,
                "passed": True,
                "score": 85.8,
                "api_calls": 0,
                "api_key": "mbt_should_not_appear",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval.latte.section.STUDY_PATH", study_path)
    loaded = load_reference(reference)
    assert loaded is not None
    assert "api_key" not in loaded
    study = load_study(study_path)
    assert study.rows[0].notes_mean == 55.0
    assert study.rows[0].no_notes_mean == 40.0
    assert study.incomplete == 1
    text = external_section(tmp_path)
    assert "External sanity check: does the model learn from feedback" in text
    assert "latte_bench.license_confirmation" in text
    assert "TODO_HUMAN" in text
    assert "example-model" in text
    assert "+15.0" in text
    assert "mbt_should_not_appear" not in text
    assert "heart" in text


def test_latte_bench_skips_without_bun_or_checkout(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("LATTE_LIVE", raising=False)
    monkeypatch.delenv("LATTE_SERVE", raising=False)
    monkeypatch.setattr(run, "bun_path", lambda: None)
    assert run.main([]) == 0
    assert "skipped: bun" in capsys.readouterr().out

    monkeypatch.setattr(run, "bun_path", lambda: "/usr/bin/bun")
    monkeypatch.setattr(run, "checkout_present", lambda: False)
    assert run.main([]) == 0
    assert "skipped: third_party/latte-bench" in capsys.readouterr().out


def test_reference_runner_does_not_vendor_bench_source():
    text = (run.RUNNER).read_text(encoding="utf-8")
    assert "function runPlan" not in text
    assert "function calibrationStatus" not in text
    assert len(text.splitlines()) < 80
