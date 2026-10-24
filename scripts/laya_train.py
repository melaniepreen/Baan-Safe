"""Optional Laya fine-tune. Skips unless a GPU or a Modal task is actually here.

Does not read or write config/decisions.yaml. The base checkpoint is the
public Hub id the town demo trains, passed on the command line.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from paths import ROOT

BASE = "convaiinnovations/laya-multilingual"
DATA = ROOT / "training" / "out" / "laya"


def _gpu() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def _modal() -> bool:
    return bool(os.environ.get("MODAL_TASK_ID") or os.environ.get("MODAL_ENVIRONMENT"))


def _blockers() -> list[str]:
    """Conditions that keep this target skip-safe (no paid GPU implied)."""
    missing: list[str] = []
    if not _gpu() and not _modal():
        missing.append("no CUDA GPU and no Modal task (MODAL_TASK_ID / MODAL_ENVIRONMENT)")
    if shutil.which("laya-train") is None:
        missing.append("laya-train is not on PATH (install laya>=0.4.14)")
    train = DATA / "train.jsonl"
    held = DATA / "held.jsonl"
    if not train.is_file() or not held.is_file():
        missing.append("training/out/laya is missing; run make export-laya")
    return missing


def main() -> int:
    if os.environ.get("LAYA_TRAIN", "").strip() != "1":
        print("skipped: set LAYA_TRAIN=1 to fine-tune")
        return 0
    blockers = _blockers()
    if blockers:
        print("skipped: Laya train not ready:")
        for item in blockers:
            print(f"  - {item}")
        return 0
    binary = shutil.which("laya-train")
    assert binary is not None
    train = DATA / "train.jsonl"
    held = DATA / "held.jsonl"
    out = Path(os.environ.get("LAYA_OUT", str(ROOT / "training" / "out" / "laya-ckpt")))
    command = [
        binary,
        "--data",
        str(train),
        "--eval",
        str(held),
        "--base",
        BASE,
        "--out",
        str(out),
    ]
    print(" ".join(command))
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
