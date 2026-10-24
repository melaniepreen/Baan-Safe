"""Agent onboarding docs stay small, templated, and pointed at real files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_onboarding_docs():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_agents.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
