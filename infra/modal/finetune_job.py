"""Correction-loop fine-tune, without a Modal import.

One dataset per task. `s1_triage` is `{text, label}` and trains with SetFit.
`s2_action`, `sapling_verdict`, and `prefs` train as a short LoRA. The legacy
messages file `eval/out/sft.jsonl` is still task `sft` and still uses that LoRA.
A dry run records a version and does not load weights. Accuracy is not invented.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from contracts.models import ModelVersion, TrainingJob
from contracts.training import S1Label, S2Action, SaplingVerdict

ROLES = ("system_1", "system_2", "orchestrator")
TASKS = ("sft", "s1_triage", "s2_action", "sapling_verdict", "prefs")


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


def parse_dataset(text: str, task: str) -> list:
    """Validate one task's JSONL. Messages tasks return a list of message lists."""

    if task not in TASKS:
        raise DatasetError(f"task {task!r} must be one of {', '.join(TASKS)}")
    if task in {"sft", "s2_action"}:
        rows = parse_jsonl(text)
        if task == "s2_action":
            _check_s2_actions(rows)
        return rows
    if task == "s1_triage":
        return _parse_objects(text, _s1_row)
    if task == "sapling_verdict":
        return _parse_objects(text, _sapling_row)
    return _parse_objects(text, _prefs_row)


def infer_task(text: str) -> str:
    """Read the first row. An explicit task still wins when the caller passes one."""

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        payload = _object_at(line_number, line)
        if "messages" in payload:
            return "sft"
        if "text" in payload and "label" in payload:
            return "s1_triage"
        if all(key in payload for key in ("policy", "evidence", "claim", "verdict")):
            return "sapling_verdict"
        if all(key in payload for key in ("prompt", "chosen", "rejected")):
            return "prefs"
        raise DatasetError(f"line {line_number} is not a known training dataset")
    raise DatasetError("dataset has no rows")


def task_for_text(text: str, task: str) -> str:
    if task:
        if task not in TASKS:
            raise DatasetError(f"task {task!r} must be one of {', '.join(TASKS)}")
        return task
    return infer_task(text)


def role_for(task: str, role: str = "") -> str:
    chosen = role.strip() if role else ""
    if not chosen:
        chosen = "system_1" if task == "s1_triage" else "system_2"
    if chosen not in ROLES:
        raise DatasetError(f"role {chosen!r} must be one of {', '.join(ROLES)}")
    return chosen


def load_task_datasets(
    dataset: str = "",
    task: str = "",
    s1: str = "",
    s2: str = "",
    sapling: str = "",
    prefs: str = "",
) -> list[tuple[str, str, str]]:
    """Return (task, path, text). Named paths are one dataset per task.

    With no named path, `dataset` is used. An empty task is inferred from the
    file. `eval/out/sft.jsonl` stays the messages path.
    """

    specs = [
        ("s1_triage", s1),
        ("s2_action", s2),
        ("sapling_verdict", sapling),
        ("prefs", prefs),
    ]
    chosen = [(item_task, path) for item_task, path in specs if path]
    if not chosen:
        if not dataset:
            raise DatasetError("pass a dataset path or one dataset per task")
        chosen = [(task, dataset)]
    loaded: list[tuple[str, str, str]] = []
    for item_task, path in chosen:
        file = Path(path)
        if not file.is_file():
            hint = ""
            if path == "eval/out/sft.jsonl":
                hint = " Run `make demo-correction-loop` or pass --dataset."
            raise DatasetError(f"{path} is missing.{hint}")
        text = file.read_text(encoding="utf-8")
        resolved = task_for_text(text, item_task)
        parse_dataset(text, resolved)
        loaded.append((resolved, path, text))
    return loaded


def messages_for(task: str, parsed: list) -> list[list[dict]]:
    """LoRA rows. SetFit does not use this. Prefs fits the chosen completion."""

    if task == "sapling_verdict":
        return sapling_as_messages(parsed)
    if task == "prefs":
        return prefs_as_messages(parsed)
    return parsed


def sapling_as_messages(rows: list[dict]) -> list[list[dict]]:
    rendered: list[list[dict]] = []
    for row in rows:
        rendered.append(
            [
                {"role": "system", "content": row["policy"]},
                {
                    "role": "user",
                    "content": f"Evidence:\n{row['evidence']}\n\nClaim:\n{row['claim']}",
                },
                {"role": "assistant", "content": row["verdict"]},
            ]
        )
    return rendered


def prefs_as_messages(rows: list[dict]) -> list[list[dict]]:
    """The rejected string stays in the stored JSONL. The LoRA target is chosen."""

    rendered: list[list[dict]] = []
    for row in rows:
        rendered.append(
            [
                {"role": "user", "content": row["prompt"]},
                {"role": "assistant", "content": row["chosen"]},
            ]
        )
    return rendered


def setfit_base_model(lora_base: str) -> str:
    """Checkpoint for System 1. FINETUNE_S1_MODEL wins. No id is hardcoded."""

    chosen = os.environ.get("FINETUNE_S1_MODEL", "").strip()
    if chosen and chosen != "TODO_HUMAN":
        return chosen
    if not lora_base or lora_base == "TODO_HUMAN":
        raise DatasetError(
            "System 1 SetFit needs FINETUNE_S1_MODEL or FINETUNE_BASE_MODEL. "
            "This job does not pick a checkpoint."
        )
    return lora_base


def dry_run_payload(runs: list[tuple[str, str, dict]]) -> dict:
    """One dataset keeps the old version file. Several datasets are a list."""

    if len(runs) == 1:
        version_id, _task, addition = runs[0]
        return {"version_id": version_id, **addition}
    return {
        "runs": [
            {"version_id": version_id, "task": task, **addition}
            for version_id, task, addition in runs
        ]
    }


def _parse_objects(text: str, check) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        rows.append(check(line_number, _object_at(line_number, line)))
    if not rows:
        raise DatasetError("dataset has no rows")
    return rows


def _object_at(line_number: int, line: str) -> dict:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"line {line_number} is not JSON") from exc
    if not isinstance(payload, dict):
        raise DatasetError(f"line {line_number} is not an object")
    return payload


def _s1_row(line_number: int, payload: dict) -> dict:
    text = payload.get("text")
    label = payload.get("label")
    if not isinstance(text, str) or not text.strip():
        raise DatasetError(f"line {line_number} needs text")
    if not isinstance(label, str):
        raise DatasetError(f"line {line_number} needs a label")
    try:
        S1Label(label)
    except ValueError as exc:
        raise DatasetError(f"line {line_number} label {label!r} is not an S1Label") from exc
    if "weight" in payload and payload["weight"] is not None:
        weight = payload["weight"]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or float(weight) < 0:
            raise DatasetError(f"line {line_number} weight must be >= 0")
    group_id = payload.get("group_id")
    if group_id is not None and (not isinstance(group_id, str) or not group_id.strip()):
        raise DatasetError(f"line {line_number} group_id must be text")
    return payload


def _sapling_row(line_number: int, payload: dict) -> dict:
    for key in ("policy", "evidence", "claim", "verdict"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DatasetError(f"line {line_number} needs {key}")
    try:
        SaplingVerdict(payload["verdict"])
    except ValueError as exc:
        raise DatasetError(
            f"line {line_number} verdict {payload['verdict']!r} is not a SaplingVerdict"
        ) from exc
    return payload


def _prefs_row(line_number: int, payload: dict) -> dict:
    for key in ("prompt", "chosen", "rejected"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DatasetError(f"line {line_number} needs {key}")
    if payload["chosen"] == payload["rejected"]:
        raise DatasetError(f"line {line_number} chosen and rejected are the same")
    return payload


def _check_s2_actions(rows: list[list[dict]]) -> None:
    for index, messages in enumerate(rows, start=1):
        assistant = next(message["content"] for message in messages if message["role"] == "assistant")
        action = assistant.splitlines()[0].strip()
        try:
            S2Action(action)
        except ValueError as exc:
            raise DatasetError(f"row {index} assistant action is not an S2Action") from exc


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
    task: str = "sft",
    parent_version_id: str | None = None,
    now: datetime | None = None,
) -> tuple[str, dict]:
    if task not in TASKS:
        raise DatasetError(f"task {task!r} must be one of {', '.join(TASKS)}")
    if role not in ROLES:
        raise DatasetError(f"role {role!r} must be one of {', '.join(ROLES)}")
    parse_dataset(dataset_text, task)
    version_id = new_version_id(dataset_text, now)
    status = "stub" if dry_run else "completed"
    if dry_run:
        note = "Dry run. No weights were trained."
    elif task == "s1_triage":
        note = "SetFit model saved on the Modal volume. Accuracy was not scored here."
    else:
        note = "LoRA adapter saved on the Modal volume. Accuracy was not scored here."
    if task != "sft":
        note = f"{note} Task {task}."
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


def train_setfit(
    rows: list[dict],
    base_model: str,
    out_dir: Path,
    *,
    max_steps: int,
) -> dict:
    """SetFit on {text, label}. Imports setfit only when a real job calls it.

    Row weights are kept on the stored JSONL. This loop does not turn them
    into a loss weight, and it does not score accuracy.
    """

    from datasets import Dataset
    from setfit import SetFitModel, Trainer, TrainingArguments

    dataset = Dataset.from_dict(
        {
            "text": [row["text"] for row in rows],
            "label": [row["label"] for row in rows],
        }
    )
    model = SetFitModel.from_pretrained(base_model)
    try:
        args = TrainingArguments(
            output_dir=str(out_dir),
            batch_size=1,
            num_epochs=1,
            max_steps=max_steps,
        )
    except TypeError:
        args = TrainingArguments(
            output_dir=str(out_dir),
            batch_size=1,
            num_epochs=max(1, max_steps),
        )
    trainer = Trainer(model=model, args=args, train_dataset=dataset)
    trainer.train()
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    return {"steps": max_steps, "trainer": "setfit", "rows": len(rows)}


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

    from infra.modal.common import resolve

    parser = argparse.ArgumentParser(description="Record a fine-tune version without training.")
    parser.add_argument("--dataset", default="eval/out/sft.jsonl")
    parser.add_argument("--task", default=os.environ.get("FINETUNE_TASK", ""))
    parser.add_argument("--s1", default="")
    parser.add_argument("--s2", default="")
    parser.add_argument("--sapling", default="")
    parser.add_argument("--prefs", default="")
    parser.add_argument("--out", default=os.environ.get("FINETUNE_DRY_RUN_DIR", "eval/out"))
    parser.add_argument("--role", default=os.environ.get("FINETUNE_ROLE", ""))
    args = parser.parse_args()
    try:
        jobs = load_task_datasets(args.dataset, args.task, args.s1, args.s2, args.sapling, args.prefs)
    except DatasetError as exc:
        raise SystemExit(str(exc)) from None
    base = resolve("modal.finetune_base_model", "FINETUNE_BASE_MODEL")
    runs: list[tuple[str, str, dict]] = []
    for item_task, _path, text in jobs:
        chosen_role = role_for(item_task, args.role)
        version_id, addition = plan_version(
            text, base, dry_run=True, role=chosen_role, task=item_task
        )
        runs.append((version_id, item_task, addition))
        print(version_id)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "modal_finetune_dry_run.json").write_text(
        json.dumps(dry_run_payload(runs), indent=2) + "\n",
        encoding="utf-8",
    )


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
