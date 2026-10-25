"""Correction-loop fine-tune. Writes a version directory on a Modal Volume.

One dataset per task. System 1 (`s1_triage`) trains SetFit on `{text, label}`.
The other tasks train a short LoRA. `eval/out/sft.jsonl` is still the messages
path. Dry runs stay on the local machine and do not boot a GPU.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import modal

from infra.modal.common import parse_gpu, redact, resolve
from infra.modal.finetune_job import (
    DatasetError,
    dry_run_payload,
    heldout_path_for,
    load_task_datasets,
    merge_registry,
    messages_for,
    parent_from_registry,
    parse_dataset,
    parse_heldout,
    plan_version,
    role_for,
    setfit_base_model,
    train_lora,
    train_setfit,
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
        "setfit>=1.1",
        "datasets>=2.14",
    ).env(
        {
            "FINETUNE_BASE_MODEL": BASE_MODEL,
            "FINETUNE_GPU": GPU_LABEL,
            "FINETUNE_S1_MODEL": os.environ.get("FINETUNE_S1_MODEL", ""),
            "HF_HOME": HF_CACHE_PATH,
        }
    )
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
    task: str = "sft",
    heldout_text: str = "",
) -> str:
    """Train one version. `heldout_text` is the s1 held-out JSONL, or empty.

    `metrics.json` next to the adapter carries the loss curve (and the
    held-out check for SetFit). `GET /training` reads it from the volume.
    """
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
        task=task,
        parent_version_id=parent_from_registry(existing),
    )
    version_dir = root / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "train.jsonl").write_text(dataset_text, encoding="utf-8")
    try:
        parsed = parse_dataset(dataset_text, task)
        if task == "s1_triage":
            heldout = parse_heldout(heldout_text) if heldout_text.strip() else None
            if heldout:
                (version_dir / "heldout.jsonl").write_text(heldout_text, encoding="utf-8")
            metrics = train_setfit(
                parsed,
                setfit_base_model(BASE_MODEL),
                version_dir / "adapter",
                max_steps=max_steps,
                heldout=heldout,
            )
        else:
            metrics = train_lora(
                messages_for(task, parsed),
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
    role: str = "",
    task: str = "",
    s1: str = "",
    s2: str = "",
    sapling: str = "",
    prefs: str = "",
    dry_run: bool = False,
) -> None:
    chosen_task = os.environ.get("FINETUNE_TASK", task).strip()
    chosen_role = os.environ.get("FINETUNE_ROLE", role).strip()
    try:
        jobs = load_task_datasets(dataset, chosen_task, s1, s2, sapling, prefs)
    except DatasetError as exc:
        raise SystemExit(str(exc)) from None
    steps = int(os.environ.get("FINETUNE_MAX_STEPS", str(max_steps)))
    length = int(os.environ.get("FINETUNE_MAX_LENGTH", str(max_length)))
    runs: list[tuple[str, str, dict]] = []
    for item_task, item_path, text in jobs:
        item_role = role_for(item_task, chosen_role)
        if dry_run:
            version_id, addition = plan_version(
                text,
                BASE_MODEL,
                dry_run=True,
                role=item_role,
                task=item_task,
            )
            runs.append((version_id, item_task, addition))
            print(version_id)
            continue
        heldout_text = ""
        if item_task == "s1_triage":
            heldout_file = heldout_path_for(item_path)
            if heldout_file is not None:
                heldout_text = heldout_file.read_text(encoding="utf-8")
                print(f"heldout: {heldout_file}")
        print(train.remote(text, steps, length, item_role, item_task, heldout_text))
    if dry_run:
        out = Path(os.environ.get("FINETUNE_DRY_RUN_DIR", "eval/out"))
        out.mkdir(parents=True, exist_ok=True)
        (out / "modal_finetune_dry_run.json").write_text(
            json.dumps(dry_run_payload(runs), indent=2) + "\n",
            encoding="utf-8",
        )
