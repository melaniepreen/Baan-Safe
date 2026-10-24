"""Modal config, JSONL planning, and the VRAM fit check. No GPU and no Modal token."""

import json

import pytest

from infra.modal.common import UnsetDecision, redact, resolve
from infra.modal.finetune_job import DatasetError, parse_jsonl, plan_version
from infra.modal.s2_cmd import check_fit
from infra.modal.vram import cheapest_gpu, fits, match_model


def test_modal_decisions_stay_unset(monkeypatch):
    for name in (
        "S1_GPU",
        "S1_MODEL_ID",
        "S2_GPU",
        "S2_MODEL_ID",
        "NEMOTRON_SIZE",
        "S2_QUANT",
        "FINETUNE_GPU",
        "FINETUNE_BASE_MODEL",
        "STT_GPU",
        "STT_MODEL_ID",
        "SAPLING_GPU",
        "SAPLING_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(UnsetDecision, match="TODO_HUMAN"):
        resolve("modal.s2_model_id", "S2_MODEL_ID")


def test_environment_overrides_todo_human(monkeypatch):
    monkeypatch.setenv("S1_MODEL_ID", "convaiinnovations/laya-multilingual")
    assert resolve("modal.s1_model_id", "S1_MODEL_ID") == "convaiinnovations/laya-multilingual"


def test_redact_hides_a_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value")
    assert "hf_secret_value" not in redact("download failed for hf_secret_value")
    assert "[redacted]" in redact("download failed for hf_secret_value")


def test_correction_jsonl_plans_a_version(tmp_path):
    row = {
        "messages": [
            {"role": "system", "content": "Label a synthetic flood-call route."},
            {"role": "user", "content": "Synthetic caller. Drinking water requested."},
            {"role": "assistant", "content": "welfare_distribution"},
        ]
    }
    text = json.dumps(row) + "\n"
    rows = parse_jsonl(text)
    assert rows[0][2]["content"] == "welfare_distribution"
    version_id, registry = plan_version(text, "TODO_HUMAN", dry_run=True)
    assert version_id.startswith("ft-")
    assert registry["jobs"][0]["status"] == "stub"
    assert registry["versions"][0]["parent_version_id"] is None
    with pytest.raises(DatasetError):
        parse_jsonl("")


def test_demo_4b_fits_a_t4_and_70b_bf16_does_not_fit_a_40gb_a100():
    nano = match_model("nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1", "4B")
    seventy = match_model("nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "70B")
    assert nano is not None and seventy is not None
    assert fits(nano, "bf16", "T4")
    assert cheapest_gpu(nano, "bf16") == "T4"
    assert not fits(seventy, "bf16", "A100-40GB")
    assert not fits(seventy, "bf16", "A100-80GB")
    assert fits(seventy, "bf16", "H200")
    assert cheapest_gpu(seventy, "fp8") == "A100-80GB"
    with pytest.raises(SystemExit, match="Refusing"):
        check_fit(seventy["repo"], "70B", "bf16", "T4")
    with pytest.raises(SystemExit, match="fp8"):
        check_fit(nano["repo"], "4B", "fp8", "T4")


def test_app_modules_import_when_a_human_exports_the_env(monkeypatch):
    pytest.importorskip("modal")
    monkeypatch.setenv("S1_GPU", "cpu")
    monkeypatch.setenv("S1_MODEL_ID", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
    monkeypatch.setenv("S2_GPU", "T4")
    monkeypatch.setenv("S2_MODEL_ID", "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1")
    monkeypatch.setenv("NEMOTRON_SIZE", "4B")
    monkeypatch.setenv("S2_QUANT", "bf16")
    monkeypatch.setenv("FINETUNE_GPU", "T4")
    monkeypatch.setenv("FINETUNE_BASE_MODEL", "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1")
    monkeypatch.setenv("STT_GPU", "cpu")
    monkeypatch.setenv("STT_MODEL_ID", "openai/whisper-small")
    monkeypatch.setenv("SAPLING_GPU", "L40S")
    monkeypatch.setenv("SAPLING_MODEL_ID", "MubitLabs/banyan-sapling")
    # Importing builds the Modal image definition. It does not deploy.
    import sys

    sys.modules.pop("infra.modal.sapling_app", None)
    import infra.modal.s1_app as s1
    import infra.modal.s2_app as s2
    import infra.modal.finetune_app as ft
    import infra.modal.stt_app as stt
    import infra.modal.sapling_app as sapling

    assert s1.GPU is None
    assert s2.GPU == "T4"
    assert ft.GPU == "T4"
    assert stt.GPU is None
    assert sapling.GPU == "L40S"
    assert sapling.MODEL_ID == "MubitLabs/banyan-sapling"
    sys.modules.pop("infra.modal.sapling_app", None)
