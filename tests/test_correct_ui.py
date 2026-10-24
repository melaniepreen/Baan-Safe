"""The operator correction form sends a v1 body and does not invent labels."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from contracts.training import S1Label, S2Action, SaplingVerdict
from training.log import read_events

ROOT = Path(__file__).resolve().parents[1]


def _node(script: str) -> object:
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_closed_enums_match_the_training_contract():
    tasks = _node(
        "import { TASKS } from './ui/correct.js';"
        "process.stdout.write(JSON.stringify(TASKS));"
    )
    assert tasks["s1_triage"] == [item.value for item in S1Label]
    assert tasks["s2_action"] == [item.value for item in S2Action]
    assert tasks["sapling_verdict"] == [item.value for item in SaplingVerdict]


def test_v1_body_fills_task_and_input_ref_for_each_path():
    body = _node(
        """
        import { buildCorrectionBody } from './ui/correct.js';
        const turns = [
          { t_ms: 0, speaker: 'caller', text: 'We need drinking water.' },
          { t_ms: 4000, speaker: 'caller', text: 'น้ำในบ้านหมด' },
        ];
        const water = {
          case_id: 'F01',
          transcript: turns,
          fields: { needs: ['water'] },
          policy_flags: ['safeguarding', 'NIEMS-COLOR-RED'],
          memory_context: [{ memory_id: 'mem-1', kind: 'similar_case', summary: 'x', relevance: 1 }],
        };
        const rescue = {
          case_id: 'F10',
          transcript: [{ t_ms: 0, speaker: 'caller', text: 'Water is rising.' }],
          fields: { needs: ['rescue'] },
          policy_flags: [],
          memory_context: [],
        };
        const aid = {
          case_id: 'F17',
          transcript: [{ turn_id: 'turn-aid', t_ms: 0, speaker: 'caller', text: 'The payment was refused.' }],
          fields: { needs: ['aid_payment'] },
          policy_flags: ['aid_exception'],
          memory_context: [],
        };
        const rows = {
          s1: buildCorrectionBody({
            caseState: water,
            decision: { source_outcomes: [{ system: 'system_1', route: 'welfare_distribution', needs: ['water'] }] },
            outputCorrect: 'sphere_water_short',
            reason: '  Drinking water, not a general patient. ',
            policyVersion: 'abc',
          }),
          s2: buildCorrectionBody({
            caseState: rescue,
            decision: {
              next_action: 'escalate_to_supervisor',
              source_outcomes: [{ system: 'system_2', route: 'rescue_coordination', needs: ['rescue'] }],
            },
            outputCorrect: 'request_more_evidence',
            reason: 'The depth is still unknown.',
            policyVersion: '',
          }),
          sapling: buildCorrectionBody({
            caseState: aid,
            decision: {
              next_action: 'escalate_to_supervisor',
              policy_notes: ['sapling_verdict=unsure'],
              source_outcomes: [{ system: 'system_2', route: 'aid_caseworker', needs: ['aid_payment'] }],
            },
            outputCorrect: 'missing',
            reason: 'The eligibility rule was not in the call.',
            policyVersion: '',
          }),
        };
        process.stdout.write(JSON.stringify(rows));
        """
    )
    s1 = body["s1"]
    assert s1["task"] == "s1_triage"
    assert s1["output_correct"] == "sphere_water_short"
    assert s1["reason"] == "Drinking water, not a general patient."
    assert s1["corrected_by"] == "operator"
    assert s1["source"] == "human"
    assert "output_model" not in s1
    assert s1["input_ref"] == {
        "case_id": "F01",
        "turn_ids": ["F01:0:0", "F01:1:4000"],
        "lang": "mixed",
        "policy_ids": ["NIEMS-COLOR-RED"],
        "memory_ref": "mem-1",
    }
    assert s1["policy_version"] == "abc"
    assert s1["model_version"] == "s1@stub"

    s2 = body["s2"]
    assert s2["task"] == "s2_action"
    assert s2["output_model"] == "escalate_to_supervisor"
    assert s2["input_ref"]["lang"] == "en"
    assert s2["input_ref"]["memory_ref"] is None
    assert "policy_version" not in s2

    sapling = body["sapling"]
    assert sapling["task"] == "sapling_verdict"
    assert sapling["output_model"] == "unsure"
    assert sapling["input_ref"]["turn_ids"] == ["turn-aid"]
    assert sapling["model_version"] == "sapling@stub"


def test_form_body_is_logged_for_a_fixture_case():
    fixture = json.loads((ROOT / "fixtures" / "scenarios" / "F01.json").read_text(encoding="utf-8"))
    with TestClient(app) as client:
        decision = client.post("/triage", json=fixture["case_state"])
        assert decision.status_code == 200
        version = client.get("/policies/labels").json()["version"]
        proc = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                """
                import { buildCorrectionBody } from './ui/correct.js';
                const raw = JSON.parse(process.argv[1]);
                const body = buildCorrectionBody({
                  caseState: raw.case_state,
                  decision: raw.decision,
                  outputCorrect: 'sphere_water_short',
                  reason: 'The call is a drinking-water request.',
                  policyVersion: raw.policy_version,
                });
                process.stdout.write(JSON.stringify(body));
                """,
                json.dumps(
                    {
                        "case_state": fixture["case_state"],
                        "decision": decision.json(),
                        "policy_version": version,
                    }
                ),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        correction = json.loads(proc.stdout)
        assert correction["task"] == "s1_triage"
        assert correction["input_ref"]["case_id"] == "F01"
        assert correction["input_ref"]["turn_ids"]
        assert correction["input_ref"]["lang"] == "en"
        created = client.post("/cases", json={"fixture_id": "F01"})
        assert created.status_code == 200
        logged = client.post("/cases/F01/corrections", json=correction)
        assert logged.status_code == 200, logged.text
        stored = logged.json()["correction"]
        assert stored["task"] == "s1_triage"
        assert stored["turn_ids"] == correction["input_ref"]["turn_ids"]
        assert stored["lang"] == "en"
        assert stored["output_correct"] == "sphere_water_short"
        events = read_events()
        assert len(events) == 1
        assert events[0].task == "s1_triage"
        assert events[0].output_correct.value == "sphere_water_short"
        assert events[0].input_ref.case_id == "F01"
        assert events[0].input_ref.turn_ids == correction["input_ref"]["turn_ids"]
        assert events[0].source == "human"
        assert events[0].corrected_by == "operator"


def test_pages_only_ask_for_the_label_and_a_reason():
    player = (ROOT / "ui" / "player.html").read_text(encoding="utf-8")
    sim = (ROOT / "ui" / "sim" / "sim.js").read_text(encoding="utf-8")
    module = (ROOT / "ui" / "correct.js").read_text(encoding="utf-8")
    assert 'from "./correct.js"' in player or "from './correct.js'" in player
    assert 'from "../correct.js"' in sim
    assert "Correct this" in player
    assert "mountCorrectForm" in sim
    assert 'select.name = "output_correct"' in module
    assert 'reason.name = "reason"' in module
    assert "name = \"task\"" not in module
    assert "name = \"input_ref\"" not in module
