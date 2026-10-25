"""`make eval-gate`: SetFit held-out accuracy floor and RL critical under-triage ceiling."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eval import gate

ROOT = Path(__file__).resolve().parents[1]


def _write_registry(
    registry_dir: Path,
    versions: list[tuple[str, str, dict | None]],
) -> Path:
    """`versions` is `(version_id, notes, metrics)` oldest first, like the registry appends."""

    registry_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "versions": [
            {
                "version_id": version_id,
                "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "role": "system_1",
                "training_job_id": f"job-{version_id}",
                "notes": notes,
            }
            for version_id, notes, _ in versions
        ],
        "jobs": [],
    }
    path = registry_dir / "registry.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    for version_id, _, metrics in versions:
        if metrics is None:
            continue
        folder = registry_dir / "versions" / version_id
        folder.mkdir(parents=True)
        (folder / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return path


def _setfit_metrics(accuracy: float | None) -> dict:
    metrics = {"trainer": "setfit", "rows": 18, "loss_curve": [{"step": 1, "loss": 0.4}]}
    if accuracy is not None:
        metrics["heldout"] = {"rows": 8, "accuracy": accuracy, "per_label": {}}
    return metrics


def _write_run(path: Path, critical_under_by_epoch: list[int | None]) -> Path:
    epochs = []
    for index, value in enumerate(critical_under_by_epoch, start=1):
        epoch = {"epoch": index, "episodes": 48, "correct": 20, "under_triage": 7}
        if value is not None:
            epoch["critical_under"] = value
        epochs.append(epoch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "baansafe.rl_run.v1", "epochs": epochs}), encoding="utf-8")
    return path


@pytest.fixture
def setfit_registry(tmp_path, monkeypatch) -> Path:
    path = _write_registry(
        tmp_path / "registry",
        [("ft-20261025T050000Z-aaaa1111", "SetFit model saved on the Modal volume. Task s1_triage.", _setfit_metrics(0.875))],
    )
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(path))
    return path


@pytest.fixture
def snapshot_root(tmp_path) -> Path:
    root = tmp_path / "snapshots"
    _write_run(root / "20260101T0000Z-x" / "run.json", [5, 2])
    return root


def test_setfit_passes_at_floor_and_fails_above(setfit_registry):
    check = gate.check_setfit(0.85)
    assert check.status == "pass"
    assert "ft-20261025T050000Z-aaaa1111" in check.detail
    assert "0.875" in check.detail and "0.850" in check.detail

    check = gate.check_setfit(0.9)
    assert check.status == "fail"
    assert "ft-20261025T050000Z-aaaa1111" in check.detail
    assert "0.875" in check.detail and "0.900" in check.detail


def test_setfit_skips_without_registry(tmp_path, monkeypatch):
    missing = tmp_path / "none" / "registry.json"
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(missing))
    check = gate.check_setfit(0.85)
    assert check.status == "skip"
    assert check.detail == "no SetFit held-out metrics at registry.json"
    assert str(tmp_path) not in check.detail


def test_setfit_skips_when_only_version_is_sft(tmp_path, monkeypatch):
    lora = {"trainer": "lora", "rows": 36, "heldout": {"rows": 4, "accuracy": 0.99}}
    path = _write_registry(
        tmp_path / "registry",
        [("ft-20261025T040000Z-bbbb2222", "LoRA adapter saved on the Modal volume.", lora)],
    )
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(path))
    check = gate.check_setfit(0.85)
    assert check.status == "skip"
    assert check.detail.startswith("no SetFit held-out metrics at ")


def test_setfit_uses_newest_version_that_has_heldout(tmp_path, monkeypatch):
    path = _write_registry(
        tmp_path / "registry",
        [
            ("ft-20261025T010000Z-cccc3333", "SetFit model saved on the Modal volume. Task s1_triage.", _setfit_metrics(0.5)),
            ("ft-20261025T020000Z-dddd4444", "SetFit model saved on the Modal volume. Task s1_triage.", _setfit_metrics(0.875)),
            ("ft-20261025T030000Z-eeee5555", "SetFit model saved on the Modal volume. Task s1_triage.", _setfit_metrics(None)),
        ],
    )
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(path))
    check = gate.check_setfit(0.85)
    assert check.status == "pass"
    assert "ft-20261025T020000Z-dddd4444" in check.detail


def test_rl_compares_last_epoch_against_last_snapshot(tmp_path, snapshot_root):
    current = _write_run(tmp_path / "out" / "run.json", [9, 2])
    check = gate.check_rl(current, snapshot_root)
    assert check.status == "pass"
    assert "20260101T0000Z-x" in check.detail
    assert "2 <= 2" in check.detail

    _write_run(current, [1, 3])
    check = gate.check_rl(current, snapshot_root)
    assert check.status == "fail"
    assert "3 > 2" in check.detail
    assert "20260101T0000Z-x" in check.detail


def test_rl_picks_the_lexically_last_snapshot(tmp_path, snapshot_root):
    _write_run(snapshot_root / "20250101T0000Z-older" / "run.json", [0])
    (snapshot_root / "20270101T0000Z-no-run").mkdir()
    current = _write_run(tmp_path / "out" / "run.json", [1])
    check = gate.check_rl(current, snapshot_root)
    assert check.status == "pass"
    assert "20260101T0000Z-x" in check.detail


def test_rl_skips_when_run_or_snapshot_is_missing(tmp_path, snapshot_root):
    missing = tmp_path / "out" / "run.json"
    check = gate.check_rl(missing, snapshot_root)
    assert check.status == "skip"
    assert str(tmp_path) not in check.detail

    current = _write_run(missing, [2, None])
    assert gate.check_rl(current, snapshot_root).status == "skip"

    _write_run(current, [2])
    check = gate.check_rl(current, tmp_path / "no-snapshots")
    assert check.status == "skip"
    assert str(tmp_path) not in check.detail

    empty = tmp_path / "empty-snapshots"
    empty.mkdir()
    assert gate.check_rl(current, empty).status == "skip"


def test_main_exit_codes_and_output(tmp_path, monkeypatch, capsys, setfit_registry, snapshot_root):
    current = _write_run(tmp_path / "out" / "run.json", [2])
    base = ["--rl-run", str(current), "--snapshots", str(snapshot_root)]

    assert gate.main(base) == 0
    out = capsys.readouterr().out
    assert "[PASS] setfit_heldout_accuracy:" in out
    assert "[PASS] rl_critical_under:" in out
    assert out.rstrip().endswith("eval-gate: ok")
    assert str(tmp_path) not in out

    _write_run(current, [3])
    assert gate.main(base) == 1
    out = capsys.readouterr().out
    assert "[FAIL] rl_critical_under:" in out
    assert "eval-gate: FAILED (1)" in out
    assert str(tmp_path) not in out

    assert gate.main([*base, "--min-accuracy", "0.9"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] setfit_heldout_accuracy:" in out
    assert "eval-gate: FAILED (2)" in out


def test_main_reads_min_accuracy_from_env(monkeypatch, capsys, setfit_registry, snapshot_root, tmp_path):
    current = _write_run(tmp_path / "out" / "run.json", [2])
    monkeypatch.setenv(gate.MIN_ACCURACY_ENV, "0.9")
    assert gate.main(["--rl-run", str(current), "--snapshots", str(snapshot_root)]) == 1
    assert "[FAIL] setfit_heldout_accuracy:" in capsys.readouterr().out
    assert gate.main(["--rl-run", str(current), "--snapshots", str(snapshot_root), "--min-accuracy", "0.8"]) == 0
    capsys.readouterr()


def test_main_skips_pass_unless_strict(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(tmp_path / "none" / "registry.json"))
    args = ["--rl-run", str(tmp_path / "none" / "run.json"), "--snapshots", str(tmp_path / "none")]

    assert gate.main(args) == 0
    out = capsys.readouterr().out
    assert out.count("[SKIP]") == 2
    assert "eval-gate: ok" in out
    assert str(tmp_path) not in out

    assert gate.main([*args, "--strict"]) == 1
    out = capsys.readouterr().out
    assert out.count("[SKIP]") == 2
    assert "eval-gate: FAILED (2)" in out
    assert str(tmp_path) not in out


def test_main_uses_rl_run_path_env_by_default(tmp_path, monkeypatch, capsys, snapshot_root):
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(tmp_path / "none" / "registry.json"))
    current = _write_run(tmp_path / "env" / "run.json", [3])
    monkeypatch.setenv("RL_RUN_PATH", str(current))
    assert gate.main(["--snapshots", str(snapshot_root)]) == 1
    assert "[FAIL] rl_critical_under:" in capsys.readouterr().out


def test_module_entry_point(tmp_path):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "TRAINING_REGISTRY_PATH": str(tmp_path / "none" / "registry.json"),
    }
    env.pop(gate.MIN_ACCURACY_ENV, None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "eval.gate",
            "--rl-run",
            str(tmp_path / "none" / "run.json"),
            "--snapshots",
            str(tmp_path / "none"),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("[SKIP]") == 2
    assert "eval-gate: ok" in proc.stdout
    assert str(tmp_path) not in proc.stdout
