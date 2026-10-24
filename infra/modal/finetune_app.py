"""Correction-loop fine-tune. Writes a version directory on a Modal Volume.

Returns the version id. The dataset is the messages JSONL from
eval/correction_loop.py. Dry runs stay on the local machine and do not boot a GPU.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import modal

from infra.modal.common import parse_gpu, redact, resolve
from infra.modal.finetune_job import (
    DatasetError,
    merge_registry,
    parent_from_registry,
    parse_jsonl,
    plan_version,
    train_lora,
)
from infra.modal.runtime import (
    HF_CACHE_PATH,
    VERSIONS_PATH,
    hf_cache,
    hf_secret,
    mubit_secret,
    versions,
    with_repo,
)
from infra.modal.s2_cmd import check_fit
from infra.modal.vram import match_model, weight_gib

BASE_MODEL = resolve("modal.finetune_base_model", "FINETUNE_BASE_MODEL")
GPU = parse_gpu(resolve("modal.finetune_gpu", "FINETUNE_GPU"), allow_cpu=True)
GPU_LABEL = "cpu" if GPU is None else GPU
_known = match_model(BASE_MODEL, "")
if _known is not None and GPU is None and weight_gib(_known["params"], "bf16") > 12:
    raise SystemExit(
        f"{_known['label']} bf16 weights do not fit a CPU fine-tune. "
        "Set FINETUNE_GPU. See infra/HARDWARE.md."
    )
if GPU is not None:
    check_fit(BASE_MODEL, "", "bf16", GPU)

image = with_repo(
    modal.Image.debian_slim(python_version="3.12").pip_install(
        "torch",
        "transformers>=4.46",
        "peft>=0.13",
        "accelerate>=1.0",
        "sentencepiece",
        "protobuf",
        "pydantic>=2.6",
        "pyyaml>=6",
        "huggingface_hub",
    )
).env(
    {
        "FINETUNE_BASE_MODEL": BASE_MODEL,
        "FINETUNE_GPU": GPU_LABEL,
        "HF_HOME": HF_CACHE_PATH,
    }
)

app = modal.App("baansafe-finetune", image=image)
cache = hf_cache()
volume = versions()


def _memory_mb() -> int:
    model = match_model(BASE_MODEL, "")
    if model is None:
        return 16384
    return max(8192, min(131072, int((weight_gib(model["params"], "bf16") + 8) * 1024)))


@app.function(
    image=image,
    gpu=GPU,
    memory=_memory_mb(),
    timeout=60 * 60,
    secrets=[hf_secret(), mubit_secret()],
    volumes={VERSIONS_PATH: volume, HF_CACHE_PATH: cache},
)
def train(
    dataset_text: str,
    max_steps: int = 20,
    max_length: int = 512,
    role: str = "system_2",
) -> str:
    volume.reload()
    root = Path(VERSIONS_PATH)
    registry_path = root / "registry.json"
    existing = None
    if registry_path.is_file():
        existing = json.loads(registry_path.read_text(encoding="utf-8"))
    version_id, addition = plan_version(
        dataset_text,
        BASE_MODEL,
        dry_run=False,
        role=role,
        parent_version_id=parent_from_registry(existing),
    )
    version_dir = root / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "train.jsonl").write_text(dataset_text, encoding="utf-8")
    try:
        rows = parse_jsonl(dataset_text)
        metrics = train_lora(
            rows,
            BASE_MODEL,
            version_dir / "adapter",
            gpu_name=GPU_LABEL,
            max_steps=max_steps,
            max_length=max_length,
        )
    except Exception as exc:
        message = redact(str(exc))[:500]
        addition["jobs"][0]["status"] = "failed"
        addition["jobs"][0]["notes"] = message
        addition["versions"][0]["notes"] = message
        merged = merge_registry(existing, addition)
        registry_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        volume.commit()
        raise RuntimeError(redact(str(exc))) from None
    (version_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n",
        encoding="utf-8",
    )
    merged = merge_registry(existing, addition)
    registry_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    volume.commit()
    cache.commit()
    return version_id


@app.local_entrypoint()
def main(
    dataset: str = "eval/out/sft.jsonl",
    max_steps: int = 20,
    max_length: int = 512,
    role: str = "system_2",
    dry_run: bool = False,
) -> None:
    path = Path(dataset)
    if not path.is_file():
        raise SystemExit(
            f"{path} is missing. Run `make demo-correction-loop` or pass --dataset."
        )
    text = path.read_text(encoding="utf-8")
    try:
        parse_jsonl(text)
    except DatasetError as exc:
        raise SystemExit(str(exc)) from None
    if dry_run:
        version_id, addition = plan_version(text, BASE_MODEL, dry_run=True, role=role)
        out = Path(os.environ.get("FINETUNE_DRY_RUN_DIR", "eval/out"))
        out.mkdir(parents=True, exist_ok=True)
        (out / "modal_finetune_dry_run.json").write_text(
            json.dumps({"version_id": version_id, **addition}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(version_id)
        return
    steps = int(os.environ.get("FINETUNE_MAX_STEPS", str(max_steps)))
    length = int(os.environ.get("FINETUNE_MAX_LENGTH", str(max_length)))
    chosen_role = os.environ.get("FINETUNE_ROLE", role)
    print(train.remote(text, steps, length, chosen_role))
