"""Correction-loop fine-tune, without a Modal import.

The dataset is the messages JSONL written by eval/correction_loop.py.
A dry run records a version and does not load weights. A real run is a short
LoRA over that JSONL. It does not invent an accuracy number.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from contracts.models import ModelVersion, TrainingJob

ROLES = ("system_1", "system_2", "orchestrator")


class DatasetError(ValueError):
    """The JSONL is not the correction-loop messages shape."""


def parse_jsonl(text: str) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"line {line_number} is not JSON") from exc
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list) or not messages:
            raise DatasetError(f"line {line_number} needs a messages list")
        roles = []
        for message in messages:
            if not isinstance(message, dict):
                raise DatasetError(f"line {line_number} has a non-object message")
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise DatasetError(
                    f"line {line_number} messages must be system, user, or assistant text"
                )
            roles.append(role)
        if "assistant" not in roles:
            raise DatasetError(f"line {line_number} has no assistant turn")
        rows.append(messages)
    if not rows:
        raise DatasetError("dataset has no rows")
    return rows


def new_version_id(dataset_text: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(dataset_text.encode("utf-8")).hexdigest()[:8]
    return f"ft-{stamp}-{digest}"


def plan_version(
    dataset_text: str,
    base_model: str,
    *,
    dry_run: bool,
    role: str = "system_2",
    parent_version_id: str | None = None,
    now: datetime | None = None,
) -> tuple[str, dict]:
    if role not in ROLES:
        raise DatasetError(f"role {role!r} must be one of {', '.join(ROLES)}")
    parse_jsonl(dataset_text)
    version_id = new_version_id(dataset_text, now)
    status = "stub" if dry_run else "completed"
    note = (
        "Dry run. No weights were trained."
        if dry_run
        else "LoRA adapter saved on the Modal volume. Accuracy was not scored here."
    )
    version = ModelVersion(
        version_id=version_id,
        model_name=base_model,
        role=role,  # type: ignore[arg-type]
        parent_version_id=parent_version_id,
        training_job_id=f"job-{version_id}",
        notes=note,
    )
    job = TrainingJob(
        job_id=f"job-{version_id}",
        status=status,  # type: ignore[arg-type]
        dataset_path=f"/vol/versions/{version_id}/train.jsonl",
        base_model=base_model,
        target_version_id=version_id,
        notes=note,
    )
    registry = {
        "versions": [version.model_dump(mode="json")],
        "jobs": [job.model_dump(mode="json")],
    }
    return version_id, registry


def merge_registry(existing: dict | None, addition: dict) -> dict:
    base = existing if isinstance(existing, dict) else {}
    versions = list(base.get("versions") or [])
    jobs = list(base.get("jobs") or [])
    versions.extend(addition["versions"])
    jobs.extend(addition["jobs"])
    return {"versions": versions, "jobs": jobs}


def parent_from_registry(existing: dict | None) -> str | None:
    versions = (existing or {}).get("versions") or []
    if not versions:
        return None
    last = versions[-1]
    if isinstance(last, dict):
        return last.get("version_id")
    return None


def write_registry(directory: Path, registry: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "registry.json").write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )


def train_lora(
    rows: list[list[dict]],
    base_model: str,
    out_dir: Path,
    *,
    gpu_name: str,
    max_steps: int,
    max_length: int,
) -> dict:
    """Short LoRA. Imports torch only when a real job calls it."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    token = _hf_token()
    tokenizer = AutoTokenizer.from_pretrained(base_model, token=token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    use_cuda = torch.cuda.is_available()
    if use_cuda and gpu_name != "T4" and torch.cuda.is_bf16_supported():
        dtype = torch.bfloat16
    elif use_cuda:
        dtype = torch.float16
    else:
        dtype = torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=dtype,
        device_map="auto" if use_cuda else None,
        token=token,
    )
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    targets = _lora_targets(model)
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=targets,
        ),
    )
    device = torch.device("cuda" if use_cuda else "cpu")
    if not use_cuda:
        model.to(device)
    model.train()
    optim = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-4)
    encoded = [_encode(tokenizer, messages, max_length) for messages in rows]
    encoded = [item for item in encoded if item is not None]
    if not encoded:
        raise DatasetError("every row was empty after truncation")
    last_loss = None
    steps = 0
    for step in range(max_steps):
        input_ids, labels = encoded[step % len(encoded)]
        batch_ids = torch.tensor([input_ids], device=device)
        batch_labels = torch.tensor([labels], device=device)
        optim.zero_grad(set_to_none=True)
        loss = model(input_ids=batch_ids, labels=batch_labels).loss
        loss.backward()
        optim.step()
        last_loss = float(loss.detach().float().cpu())
        steps = step + 1
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"steps": steps, "last_loss": last_loss, "trainable_parameters": int(trainable)}


def _hf_token() -> str | None:
    import os

    token = os.environ.get("HF_TOKEN", "").strip()
    return token or None


def _lora_targets(model) -> list[str]:
    found: set[str] = set()
    for name, _module in model.named_modules():
        leaf = name.rsplit(".", 1)[-1]
        if leaf in {"q_proj", "k_proj", "v_proj", "o_proj"}:
            found.add(leaf)
    if found:
        return sorted(found)
    linear = []
    import torch

    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            linear.append(name.rsplit(".", 1)[-1])
            if len(set(linear)) >= 4:
                break
    picked = sorted(set(linear))
    if not picked:
        raise DatasetError("no Linear modules to attach LoRA to")
    return picked


def _encode(tokenizer, messages: list[dict], max_length: int):
    prompt, full = _render(tokenizer, messages)
    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    full_ids = tokenizer(
        full,
        add_special_tokens=False,
        truncation=True,
        max_length=max_length,
    ).input_ids
    if not full_ids:
        return None
    labels = list(full_ids)
    cutoff = min(len(prompt_ids), len(labels) - 1)
    for index in range(max(cutoff, 0)):
        labels[index] = -100
    if all(label == -100 for label in labels):
        return None
    return full_ids, labels


def _dry_run_main() -> None:
    import argparse
    import os

    from infra.modal.common import resolve

    parser = argparse.ArgumentParser(description="Record a fine-tune version without training.")
    parser.add_argument("--dataset", default="eval/out/sft.jsonl")
    parser.add_argument("--out", default=os.environ.get("FINETUNE_DRY_RUN_DIR", "eval/out"))
    parser.add_argument("--role", default=os.environ.get("FINETUNE_ROLE", "system_2"))
    args = parser.parse_args()
    text = Path(args.dataset).read_text(encoding="utf-8")
    base = resolve("modal.finetune_base_model", "FINETUNE_BASE_MODEL")
    version_id, addition = plan_version(text, base, dry_run=True, role=args.role)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "modal_finetune_dry_run.json").write_text(
        json.dumps({"version_id": version_id, **addition}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(version_id)


def _render(tokenizer, messages: list[dict]) -> tuple[str, str]:
    try:
        prompt = tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True
        )
        full = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        if isinstance(prompt, str) and isinstance(full, str) and full:
            return prompt, full
    except Exception:
        pass
    lines = [f"{message['role']}: {message['content']}" for message in messages]
    full = "\n".join(lines)
    prompt = "\n".join(lines[:-1]) + "\nassistant:"
    return prompt, full


if __name__ == "__main__":
    _dry_run_main()
