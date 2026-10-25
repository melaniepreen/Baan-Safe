"""Modal config, JSONL planning, and the VRAM fit check. No GPU and no Modal token."""

import json
import os

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
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-value")
    assert "hf_secret_value" not in redact("download failed for hf_secret_value")
    assert "[redacted]" in redact("download failed for hf_secret_value")
    assert "sk-or-test-value" not in redact("openrouter sk-or-test-value")


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


def test_policy_pin_dir_and_db_path_follow_env(monkeypatch, tmp_path):
    from ingest.db import _default_db_path
    from paths import ROOT
    from policies.service import PolicyService

    monkeypatch.delenv("POLICY_PIN_DIR", raising=False)
    monkeypatch.delenv("BAANSAFE_DB_PATH", raising=False)
    assert PolicyService().pin_dir == ROOT / "var" / "policy-pins"
    explicit = tmp_path / "pins"
    monkeypatch.setenv("POLICY_PIN_DIR", str(tmp_path / "from-env"))
    assert PolicyService(pin_dir=explicit).pin_dir == explicit
    assert PolicyService().pin_dir == tmp_path / "from-env"
    assert _default_db_path() == ROOT / "data" / "raw" / "ingest.sqlite"
    monkeypatch.setenv("BAANSAFE_DB_PATH", str(tmp_path / "demo.sqlite"))
    assert _default_db_path() == tmp_path / "demo.sqlite"


def test_gateway_app_builds_demo_asgi_with_mubit_secret_slot(monkeypatch, tmp_path):
    pytest.importorskip("modal")
    for name in (
        "S1_UPSTREAM",
        "S2_UPSTREAM",
        "SAPLING_UPSTREAM",
        "STT_UPSTREAM",
        "STT_GPU",
        "STT_MODEL_ID",
        "S1_GPU",
        "S1_MODEL_ID",
        "S2_IMPL",
        "MUBIT_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    import sys

    sys.modules.pop("infra.modal.gateway_app", None)
    import infra.modal.gateway_app as gateway

    assert gateway.STUB_ENV["S1_IMPL"] == "real"
    assert gateway.STUB_ENV["S2_IMPL"] == "stub"
    assert gateway.STUB_ENV["MEMORY_IMPL"] == "local"
    assert gateway.STUB_ENV["MEMORY_LOCAL_PATH"] == "/data/memory.jsonl"
    assert gateway.STUB_ENV["SAPLING_IMPL"] == "stub"
    assert gateway.STUB_ENV["ENRICH_IMPL"] == ""
    assert "ENRICH_IMPL" not in gateway.image_env()
    assert "MUBIT_API_KEY" not in gateway.image_env()
    assert "MUBIT_BASE_URL" not in gateway.image_env()
    assert gateway.image_env()["S1_IMPL"] == "real"
    assert gateway.image_env()["S2_IMPL"] == "stub"
    assert gateway.STUB_ENV["TRACE_PATH"].startswith("/data/")
    assert gateway.STUB_ENV["MEMORY_LOCAL_PATH"].startswith("/data/")
    assert gateway.image_env()["MEMORY_IMPL"] == "local"
    assert gateway.STUB_ENV["POLICY_PIN_DIR"].startswith("/data/")
    assert "BAANSAFE_DB_PATH" not in gateway.STUB_ENV
    assert "HF_TOKEN" not in gateway.image_env()
    assert "STT_UPSTREAM" not in gateway.image_env()
    from pathlib import Path

    from infra.modal.common import MUBIT_SECRET_NAME

    spec = gateway.web._spec_
    assert len(list(spec.secrets)) == 1
    assert spec.secrets[0].name == MUBIT_SECRET_NAME
    assert spec.gpus is None
    assert spec.cpu == 1.0
    # Demo writes on /data; the fine-tune registry is read-only on /vol.
    from infra.modal.runtime import VERSIONS_PATH

    assert VERSIONS_PATH == "/vol"
    assert set(spec.volumes) == {"/data", VERSIONS_PATH}
    assert spec.volumes[VERSIONS_PATH]._read_only is True
    assert spec.volumes["/data"]._read_only is False
    assert gateway.STUB_ENV["TRAINING_REGISTRY_PATH"] == "/vol/registry.json"
    assert gateway.STUB_ENV["RL_RUN_PATH"] == "/data/rl_run.json"
    assert gateway.image_env()["TRAINING_REGISTRY_PATH"] == "/vol/registry.json"
    from api.routes.training import VOLUME_REGISTRY_PATH

    assert VOLUME_REGISTRY_PATH == gateway.STUB_ENV["TRAINING_REGISTRY_PATH"]
    source = Path(gateway.__file__).read_text(encoding="utf-8")
    # Demo ledger is in-process; pin replicas in source (Modal may not mirror on _spec_).
    assert "max_containers=1" in source
    assert "include_source=True" in source
    assert gateway.web._is_web_endpoint()
    assert gateway._ignore(Path(".env"))
    assert gateway._ignore(Path(".git/config"))
    assert gateway._ignore(Path("var/memory.jsonl"))
    assert gateway._ignore(Path("ui/sim/index.html")) is False
    assert gateway._ignore(Path("api/main.py")) is False

    for key in ("S1_IMPL", "S2_IMPL", "MEMORY_IMPL", "SAPLING_IMPL"):
        monkeypatch.setenv(key, gateway.STUB_ENV[key])
    # Keep the local store off /data on a developer machine.
    monkeypatch.setenv("MEMORY_LOCAL_PATH", str(tmp_path / "memory.jsonl"))
    monkeypatch.delenv("ENRICH_IMPL", raising=False)
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    gateway.apply_runtime_impl()
    assert os.environ["S2_IMPL"] == "stub"
    assert os.environ["MEMORY_IMPL"] == "local"
    assert os.environ["MEMORY_LOCAL_PATH"] == str(tmp_path / "memory.jsonl")
    assert gateway.mubit_credentials_present() is False

    from fastapi.testclient import TestClient

    api = gateway.build_asgi()
    with TestClient(api) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["impl"]["S1_IMPL"] == "real"
        assert health.json()["impl"]["S2_IMPL"] == "stub"
        assert health.json()["impl"]["ENRICH_IMPL"] in {"data", "off"}
        page = client.get("/ui/sim/")
        assert page.status_code == 200
        assert "Baan-Safe" in page.text
        hosting = client.get("/hosting")
        assert hosting.status_code == 200
        body = hosting.json()
        assert body["backends"] == "s1-real"
        assert body["secrets"] is False
        assert body["memory"] == "local"
        assert body["impl"]["S1_IMPL"] == "real"
        assert body["impl"]["S2_IMPL"] == "stub"
        assert body["impl"]["MEMORY_IMPL"] == "local"
        assert body["writes"]["MEMORY_LOCAL_PATH"] == str(tmp_path / "memory.jsonl")
        assert "MEMORY_IMPL=local" in body["note"]
        assert "LLM via Mubit only" in body["note"]
        assert "stub gateway" not in body["note"].lower()
        assert "System 1" in body["note"]
        assert body["writes"]["TRACE_PATH"]
        assert body["reads"]["TRAINING_REGISTRY_PATH"] == "/vol/registry.json"
        assert body["reads"]["RL_RUN_PATH"] == "/data/rl_run.json"
        assert body["reads"]["versions_volume"] == "baansafe-versions"
        assert body["reads"]["rl_run_upload"].startswith("modal volume put baansafe-demo ")
        assert body["reads"]["page"] == "/ui/training.html"
        assert "/training" in body["note"]
        training_page = client.get("/ui/training.html")
        assert training_page.status_code == 200
        assert "training.js" in training_page.text
        training = client.get("/training")
        assert training.status_code == 200
        assert set(training.json()) >= {"finetune", "rl", "mubit_traffic", "events", "missing"}
        assert "test-key" not in training.text
        assert body["upstreams"] == {
            "S1_UPSTREAM": False,
            "S2_UPSTREAM": False,
            "SAPLING_UPSTREAM": False,
            "STT_UPSTREAM": False,
        }
        speech = client.post(
            "/stt/transcribe",
            content=b"not-audio",
            headers={"content-type": "application/octet-stream"},
        )
        assert speech.status_code == 200
        assert speech.json()["text"] == ""
        assert speech.json()["stub"] is True
        created = client.post("/cases", json={"fixture_id": "F01"})
        assert created.status_code == 200
        case_id = created.json()["case"]["case_id"]
        turned = client.post(
            f"/cases/{case_id}/turns",
            json={"t_ms": 90000, "speaker": "operator", "text": "Noted."},
        )
        assert turned.status_code == 200
        # The routed turn landed in the local store, not on /data.
        assert (tmp_path / "memory.jsonl").exists()
        trace = client.get(f"/cases/{case_id}/trace").json()
        writes = [e for e in trace if e["stage"] == "memory_write"]
        assert writes and "status=ok" in writes[-1]["notes"]
        assert "mode=local" in writes[-1]["notes"]
        triaged = client.post("/triage", json=created.json()["case"])
        assert triaged.status_code == 200


def test_gateway_s2_real_when_mubit_credentials_present(monkeypatch, tmp_path):
    pytest.importorskip("modal")
    import infra.modal.gateway_app as gateway

    monkeypatch.setenv("S1_IMPL", "real")
    monkeypatch.setenv("S2_IMPL", "stub")
    monkeypatch.setenv("MEMORY_IMPL", "local")
    monkeypatch.setenv("MEMORY_LOCAL_PATH", str(tmp_path / "memory.jsonl"))
    monkeypatch.setenv("MUBIT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    assert gateway.mubit_credentials_present() is True
    gateway.apply_runtime_impl()
    assert os.environ["S2_IMPL"] == "real"
    # Credentials promote System 2 only; memory stays BaanSafe's own store.
    assert os.environ["MEMORY_IMPL"] == "local"
    body = gateway.hosting()
    assert body["secrets"] is True
    assert body["backends"] == "live"
    assert body["memory"] == "local"
    assert body["impl"]["S2_IMPL"] == "real"
    assert body["impl"]["MEMORY_IMPL"] == "local"
    assert "LLM via Mubit only" in body["note"]
    assert "MEMORY_IMPL=local" in body["note"]
    assert "test-key-not-real" not in body["note"]
    assert "test-key-not-real" not in str(body)
    assert "traces" in body["writes"]["TRACE_PATH"]
    assert body["writes"]["MEMORY_LOCAL_PATH"].endswith("memory.jsonl")

    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    gateway.apply_runtime_impl()
    assert os.environ["S2_IMPL"] == "stub"
    assert os.environ["MEMORY_IMPL"] == "local"
    assert gateway.hosting()["secrets"] is False
    assert gateway.hosting()["backends"] == "s1-real"
    assert gateway.hosting()["memory"] == "local"


def test_gateway_memory_mubit_only_when_deployed_with_credentials(monkeypatch, tmp_path):
    """The dormant mubit path is kept: explicit MEMORY_IMPL=mubit plus the
    secret is honoured; without the secret, or when deployed mock/empty, the
    runtime is the local store."""
    pytest.importorskip("modal")
    import infra.modal.gateway_app as gateway

    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.delenv("MEMORY_LOCAL_PATH", raising=False)
    monkeypatch.setenv("MUBIT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    gateway.apply_runtime_impl()
    assert os.environ["MEMORY_IMPL"] == "mubit"
    assert os.environ["MEMORY_LOCAL_PATH"] == "/data/memory.jsonl"
    body = gateway.hosting()
    assert body["memory"] == "mubit"
    assert "test-key-not-real" not in str(body)

    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    gateway.apply_runtime_impl()
    assert os.environ["MEMORY_IMPL"] == "local"

    monkeypatch.setenv("MEMORY_IMPL", "mock")
    monkeypatch.setenv("MUBIT_API_KEY", "test-key-not-real")
    gateway.apply_runtime_impl()
    assert os.environ["MEMORY_IMPL"] == "local"


def test_mubit_secret_requires_key_and_base_url():
    pytest.importorskip("modal")
    from infra.modal.common import MUBIT_SECRET_NAME
    from infra.modal.runtime import mubit_secret

    secret = mubit_secret()
    assert secret.name == MUBIT_SECRET_NAME


def test_stt_upstream_forwards_and_invents_nothing(monkeypatch):
    pytest.importorskip("modal")
    import infra.modal.gateway_app as gateway
    from fastapi.testclient import TestClient

    captured = {}

    class _Response:
        def json(self):
            return {"text": "need a boat", "language": "en"}

    class _Client:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, content, headers):
            captured["url"] = url
            captured["content"] = content
            return _Response()

    monkeypatch.setenv("STT_UPSTREAM", "https://stt.example.test")
    monkeypatch.setattr(gateway.httpx, "AsyncClient", _Client)
    api = gateway.build_asgi()
    with TestClient(api) as client:
        speech = client.post(
            "/stt/transcribe",
            content=b"audio-bytes",
            headers={"content-type": "audio/webm"},
        )
    assert speech.status_code == 200
    assert speech.json()["text"] == "need a boat"
    assert speech.json()["stub"] is False
    assert captured["url"] == "https://stt.example.test/transcribe"
    assert captured["content"] == b"audio-bytes"

    class _Down:
        def __init__(self, timeout):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, content, headers):
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(gateway.httpx, "AsyncClient", _Down)
    with TestClient(api) as client:
        failed = client.post("/stt/transcribe", content=b"audio-bytes")
    assert failed.status_code == 200
    assert failed.json()["text"] == ""
    assert "invented" in failed.json()["note"]
    monkeypatch.setenv("STT_UPSTREAM", "TODO_HUMAN")
    with TestClient(api) as client:
        refused = client.post("/stt/transcribe", content=b"audio-bytes")
    assert refused.json()["text"] == ""
    assert refused.json()["stub"] is True
