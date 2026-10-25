"""scripts/check_owners.py: single-writer reminder keyed on branch prefix."""

from __future__ import annotations

from pathlib import Path

from paths import ROOT
from scripts import check_owners


def test_owner_branch_passes():
    assert check_owners.warnings_for("melanie/town-fixes", ["ui/sim/sim.js", "README.md"]) == []
    assert check_owners.warnings_for("moly/client-retry", ["llm/client.py"]) == []


def test_other_branch_warns_per_file():
    found = check_owners.warnings_for("feat/demo-hygiene", ["ui/sim/sim.js", "llm/client.py", "gateway/route.py"])
    assert len(found) == 2
    assert any("ui/sim/sim.js" in line and "Melanie" in line for line in found)
    assert any("llm/client.py" in line and "Moly" in line for line in found)


def test_cli_exit_codes(capsys):
    args = ["--branch", "feat/x", "--files", "ui/sim/sim.js"]
    assert check_owners.run(args) == 0
    assert "1 warning" in capsys.readouterr().out
    assert check_owners.run([*args, "--strict"]) == 1
    assert check_owners.run(["--branch", "feat/x", "--files", "README.md", "--strict"]) == 0


def test_codeowners_covers_single_writer_files():
    text = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    rules = [line.split() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    patterns = {rule[0] for rule in rules}
    for path in check_owners.SINGLE_WRITER:
        assert path in patterns or any(
            pattern.endswith("/") and path.startswith(pattern) for pattern in patterns
        ), f"{path} has no CODEOWNERS rule"
    for rule in rules:
        assert len(rule) >= 2 and all(handle.startswith("@") for handle in rule[1:]), rule
