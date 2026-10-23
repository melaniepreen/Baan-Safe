import json
from pathlib import Path

from contracts.models import CaseState, Outcome
from paths import ROOT


def test_examples_validate():
    case = json.loads((ROOT / "contracts/examples/case_state.json").read_text())
    s1 = json.loads((ROOT / "contracts/examples/outcome_s1.json").read_text())
    s2 = json.loads((ROOT / "contracts/examples/outcome_s2.json").read_text())
    CaseState.model_validate(case)
    assert Outcome.model_validate(s1).system.value == "system_1"
    assert Outcome.model_validate(s2).reasoning


def test_schemas_exported():
    folder = ROOT / "contracts" / "schemas"
    assert (folder / "CaseState.json").exists()
    assert (folder / "Outcome.json").exists()
    schema = json.loads((folder / "Priority.json").read_text())
    assert schema["enum"] == ["P1", "P2", "P3", "P4"]
