---
title: Modal infra
tags: [modal, gpu, deploy, sapling, nemotron]
files:
  - infra/modal/common.py
  - infra/modal/s2_app.py
  - infra/modal/sapling_app.py
  - infra/HARDWARE.md
  - scripts/sync_modal_secrets.py
  - scripts/sync_workspace.py
  - scripts/push_workspace.py
---

## Purpose

Modal apps for System 1, System 2, Sapling, speech-to-text, and a finetune job. GPU names and model ids in git stay `TODO_HUMAN`, so the apps refuse until a human exports them.

## Key files

- `infra/modal/common.py` — `resolve(path, env_name)`. Environment wins. `TODO_HUMAN` in either place raises `UnsetDecision`.
- `infra/modal/s1_app.py`, `s2_app.py`, `stt_app.py`, `finetune_app.py`, `sapling_app.py`.
- `infra/modal/sapling_gpu.py` — allows `L40S`, `A100-80GB`, `H100`, `H100!`, `H200`. Refuses `A6000` (not a Modal GPU string), `T4`, `L4`, `A10`, `A100-40GB`.
- `infra/modal/vram.py` — footprint tables. Not a chosen model.
- `infra/HARDWARE.md` — prices and the sizing note.
- `infra/modal/runtime.py` — Modal secret `baansafe-mubit`, key name `MUBIT_API_KEY`. The value is not in git.
- `scripts/sync_modal_secrets.py` — `make modal-secrets` from gitignored `.env`.
- `scripts/sync_workspace.py` — `make sync` (download) for both teammates: pull, `.env`, pip, Modal, secrets, push readiness.
- `scripts/push_workspace.py` — `make push` (send): Modal secrets + `git push` main. `MSG='...'` commits first (never `.env`).

## Interfaces/contracts

- `make sync` runs `scripts/sync_workspace.py`: stash + pull (ff-only, else merge), auto-resolve conflicts via `SYNC_KEEP=local|remote|manual` (default `local`), bootstrap/merge `.env` from `.env.example` without overwriting values, create/use `.venv` and `pip install` root + Modal requirements, Modal login check, then secret sync when keys exist. Exits non-zero if conflicts remain. Does not print secrets.
- `make push` runs `scripts/push_workspace.py`: syncs Modal secrets from `.env`, optionally commits with `MSG=...` (skips `.env` / `.venv` / `.vscode`), then pushes `main`. If behind origin, runs sync first (same conflict rules).
- `make modal-secrets` runs `scripts/sync_modal_secrets.py`: pushes `HF_TOKEN` / `MUBIT_API_KEY` (and optional `S2_SERVE_API_KEY`) from gitignored `.env` into `baansafe-hf` / `baansafe-mubit`. Does not print values. Does not sync `OPENROUTER_API_KEY`.
- `make modal-deploy-s1`, `modal-deploy-s2`, `modal-deploy-sapling`, `modal-deploy-stt` run `modal deploy`.
- `make modal-finetune` runs `modal run -m infra.modal.finetune_app` with `DATASET` (default `eval/out/sft.jsonl`).
- Sapling app reads `sapling.model_id` / `SAPLING_MODEL_ID` and `sapling.gpu` / `SAPLING_GPU`. It does not fall back to `MubitLabs/banyan-sapling`.
- System 2 on Modal is the self-hosted vLLM app. That is separate from `system2.hosting` (`openrouter via mubit gateway`). Do not point the LLM client at the Modal URL directly.

## Invariants

- Do not commit `HF_TOKEN`, `MUBIT_API_KEY`, or `S2_SERVE_API_KEY`. `infra/modal/common.py` lists those names.
- Importing an app module resolves config. Tests that import `sapling_app` must set env and pop the module from `sys.modules`.
- `modal.*` leaves in `config/decisions.yaml` stay `TODO_HUMAN`. They are not the product decisions `system2.*` or `sapling.*`.

## How to test

- `tests/test_modal_infra.py`, `tests/test_sapling.py` (GPU allow-list and unset model id).
- `make validate` — modal leaves are still `TODO_HUMAN`.
- Do not deploy from a test run.

## Common pitfalls

- Hardcoding a Nemotron repo id in `s2_app.py`. `modal.s2_model_id` is unset on purpose.
- Passing `A6000` as `SAPLING_GPU`. Modal will not accept it. The hardware note says L40S on Modal, A6000 only when self-hosting.
- Treating a green `make test` as a deployed app. Tests skip the GPU.

## Open TODO_HUMAN keys

- `modal.s1_gpu`, `modal.s1_model_id`
- `modal.s2_gpu`, `modal.s2_model_id`, `modal.nemotron_size`, `modal.s2_quant`
- `modal.finetune_gpu`, `modal.finetune_base_model`
- `modal.stt_gpu`, `modal.stt_model_id`
- `sapling.gpu`, `sapling.model_id`, `sapling.hosting` (product keys the Sapling app also refuses on)
