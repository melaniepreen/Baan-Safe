---
title: Training surface
tags: [training, metrics, loss-curve, finetune, mubit, rl, ui]
files:
  - api/routes/training.py
  - ui/training.html
  - ui/training.js
  - infra/modal/finetune_job.py
  - infra/modal/finetune_app.py
  - infra/modal/gateway_app.py
---

## Purpose

Make training visible. `GET /training` is one JSON document and `/ui/training.html` is the page that draws it: Mubit traffic from the recorded System 2 calls, the correction-loop fine-tune registry with inline loss curves, the RL loop report, and TrainingEvent counts. Mubit trains per-task adapters from our calls on its side and has no API for that state, so the page shows what BaanSafe can measure. Nothing here calls a model.

## Key files

- `api/routes/training.py` — the route and the pure section builders (`finetune_section`, `rl_section`, `summarize_mubit_chat`, `events_section`). Included from `api/main.py`.
- `ui/training.html`, `ui/training.js` — plain JS, no deps, inline SVG charts. Served by the same `/ui` static mount as `ui/player.html`.
- `infra/modal/finetune_job.py` — `train_lora` records `loss_curve` every step; `train_setfit` captures the embedding loss and an optional held-out check. Pure helpers: `loss_curve_from_log_history`, `loss_summary`, `setfit_loss_curve`, `heldout_metrics`, `lora_metrics`, `setfit_metrics`.
- `infra/modal/finetune_app.py` — `train()` takes `heldout_text`; the local entrypoint reads `training/out/s1_synthetic_heldout.jsonl` next to the s1 dataset (or `FINETUNE_HELDOUT`) and passes it through.
- `infra/modal/gateway_app.py` — mounts `baansafe-versions` read-only at `/vol`, sets `TRAINING_REGISTRY_PATH` and `RL_RUN_PATH`; `GET /hosting` lists them under `reads`.

## Interfaces/contracts

`GET /training` top level: `generated_at`, `finetune`, `rl`, `mubit_traffic`, `events`, `compare`, `missing`, `note`.

| Block | Source | Fields |
|---|---|---|
| `finetune` | `TRAINING_REGISTRY_PATH` (default `/vol/registry.json` when `/vol` exists, else `var/versions/registry.json`), joined with `versions/<id>/metrics.json` | `versions[]` newest first: `version_id`, `task`, `role`, `base_model`, `gpu`, `status`, `created_at`, `steps`, `rows`, `first/last/min/mean_loss`, `heldout_accuracy`, `loss_curve`, `metrics`; `decided: {base_model, gpu}` (`TODO_HUMAN` if unset, never raises) |
| `rl` | `RL_RUN_PATH` (default `eval/out/rl/run.json`) | `epochs[]` (`mean_reward`, `correct`, `under_triage`, `critical_under`, `share_s1_only/cascade/s2_only`, `s2_fallbacks`), `mubit`, `overlay` counts, `training.counts`, `finetune` note |
| `mubit_traffic` | `TRACE_PATH` rows with stage `mubit_chat` | `call_count`, `ok_count`, `error_count`, `cache_hit_count`, `distinct_sessions` (distinct `case_id` = `metadata.session_id`), `avg/p50/p95_latency_ms` (cache hits excluded), `tokens_in_total`, `tokens_out_total`, `models`, `first/last_call_at`, `kept_example_threshold: 25`, `note` |
| `events` | `TRAINING_EVENTS_PATH` (file or dir) and `training/out/*.manifest.json`, `eval/out/rl/training/*.manifest.json` | `total`, `by_task`, `by_source`, `manifests[]` |
| `compare` | `RL_COMPARE_A` / `RL_COMPARE_B` (snapshot name, dir, or `run.json`; default the memory-empty and memory-local snapshots), computed in-process by `eval/rl/compare.py` | `available`, `a`/`b` (`label`, `run_path`), `epochs[]`, `last_epoch.metrics{metric:{a,b,delta}}`, `mubit`, `overlay`, `flips{flag:{fixed_in_b,new_in_b,both}}`, `summary[]` rows the page draws as the "Memory off vs on" card |

`GET /training/episodes?filter=critical_under|under_triage|missed_human|incorrect|all&epoch=<n>&limit=<n>` (defaults `critical_under`, all epochs, 200) reads the same `RL_RUN_PATH` and returns `{run_path, filter, epoch, count, matched, total, episodes[]}`; each episode row carries `fixture_title` from `fixtures.load` (fixture index, synthetic call, RL theme, or sim caller; `null` when unknown). The page's Episodes table under the RL section re-fetches it on the filter / epoch `<select>` change. Unknown `filter` is 400.

`metrics.json` (LoRA): `trainer: lora`, `steps`, `rows`, `max_length`, `lr`, `lora_r`, `trainable_parameters`, `base_model`, `gpu`, `wall_seconds`, `loss_curve: [{step, loss}]`, `first/last/min/mean_loss`. (SetFit): `trainer: setfit`, `steps`, `rows`, `label_count`, `labels`, `base_model`, `wall_seconds`, `loss_source` (`log_history` | `callback` | `logger` | `none`), `loss_curve`, the four summaries, and `heldout: {rows, accuracy, per_label{support, precision, recall}}` when held-out rows were passed.

SetFit loss capture order: `trainer.st_trainer.state.log_history`, then `trainer.state.log_history` (entries with `embedding_loss` or `loss`), then a `transformers.TrainerCallback` passed as `callbacks=` when the `Trainer` accepts it, then a `logging.Handler` on the `setfit` and `sentence_transformers` loggers parsing `{'embedding_loss': x, ...}` lines. `logging_steps=1` is requested so every step lands in `log_history`.

Hosted env: `TRAINING_REGISTRY_PATH=/vol/registry.json`, `RL_RUN_PATH=/data/rl_run.json`. The RL report is gitignored and not in the image; upload it with `modal volume put baansafe-demo eval/out/rl/run.json rl_run.json`.

## Invariants

- Every file is optional. A missing or unreadable one is named in `missing` and its block is empty; the route never returns 500 for an absent file.
- Paths in the response are repo-relative, a `/vol` or `/data` volume path, or the bare file name. Nothing else leaks.
- No secret is read or printed. The page does not name `MUBIT_`, `OPENROUTER`, or `Bearer`.
- Dry runs and the API never import torch, peft, setfit, datasets, or transformers. Those imports stay inside `train_lora` / `train_setfit`.
- Accuracy is not invented. `heldout` exists only when a held-out file was present; the LoRA block has no accuracy.
- The gateway mounts the versions volume read-only. Only `finetune_app.py` writes to it.
- `frontend-prototype/` and `ui/sim/` are untouched by this surface.

## How to test

- `tests/test_training_surface.py` — tmp registry + metrics + run.json + traces + events; the helper extraction with a fake trainer; page served and free of secret names.
- `tests/test_eval_tools.py` — `compare` section with env overrides and defaults, `/training/episodes` filters, `fixture_title`, `rl-compare`, `eval-gate`, `mubit-requests`.
- `tests/test_modal_infra.py` — `/vol` read-only on the gateway spec, `/hosting.reads`, `/ui/training.html` and `/training` on the demo ASGI.
- `make serve` then open `/ui/training.html`. `RL_RUN_PATH=eval/out/rl/run.json TRACE_PATH=eval/out/rl/traces.jsonl make serve` shows a real RL run.
- `make test`, `make validate`.

## Common pitfalls

- Expecting a loss curve on a dry-run version. Dry runs write a registry row and no `metrics.json`.
- Reading `mubit_traffic` as Mubit's training state. It is our request log; kept-example count and adapter status are in the Mubit console.
- Pointing `TRAINING_REGISTRY_PATH` at a file but keeping `metrics.json` elsewhere. The join is `<registry dir>/versions/<id>/metrics.json`.
- Shipping `eval/out` in the Modal image. It is in `.dockerignore`; use the volume copy.
- Adding a chart library. The page is plain JS with inline SVG.

## Open TODO_HUMAN keys

- `ui.framework` — the page stays framework-free until this is set.
- `llm.token_price_usd` — token totals are shown; cost stays null.
- `correction_loop.graduation_threshold`, `learning_eval.promotion` — the surface reports runs; it does not promote.
