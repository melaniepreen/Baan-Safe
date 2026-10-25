---
title: RL loop
tags: [rl, overlay, cascade, graduation, demotion, bandit]
files:
  - eval/rl/run.py
  - eval/rl/compare.py
  - eval/rl/learner.py
  - eval/rl/reward.py
  - eval/rl/themes.py
  - gateway/overlay.py
  - config/routing.yaml
---

## Purpose

Score System 1 / System 2 outcomes in a reward loop. A System 1 escalate cascades to System 2 in the same turn. Consistent correct System 2 decisions graduate to a System 1 rule; P1 and complex patterns become a recommendation instead. System 1 under-triage demotes a pattern to System 2. A shadow bandit learns routing but never routes. Every scored episode appends a sim `TrainingEvent`.

## Key files

- `eval/rl/run.py` — `python -m eval.rl --s2 live|replay|fake`. Writes `eval/out/rl/run.json`, `rl.md`, `overlay.json`, `s2_cache.jsonl`.
- `eval/rl/compare.py` — `make rl-compare [A=<snapshot> B=<snapshot>]` (`python -m eval.rl.compare`). Pairs two `eval/snapshots/rl/<name>/run.json` files, headline = last epoch of each, writes `eval/out/rl_compare.md` + `.json`. Default A/B = first/last folder, i.e. memory off vs on. `GET /training/compare` serves the same dict; snapshot names are checked against the folder listing (no path traversal).
- `eval/rl/themes.py` — eight authored themes with variants and settled truth.
- `eval/rl/reward.py` — priority distance, route, human, cost, and correctness scoring.
- `eval/rl/learner.py` — graduation streaks, demotion, Beta(1,1) shadow bandit.
- `gateway/overlay.py` — coarse/narrow signatures, `Overlay`, `RL_OVERLAY` opt-in. Live-path code.
- `gateway/route.py` — `handle(case, use_stubs, overlay)`; cascade and the fallback guard.
- `api/routes/endpoints.py` — `GET /rl/run` serves `run.json`, else 404 saying to run `make rl-loop`.

## Interfaces/contracts

- `Overlay` schema `baansafe.rl_overlay.v1`: `graduation_threshold`, `graduated`, `recommendations`, `demoted`. Narrow signatures promote; coarse signatures demote. A narrow signature is the coarse signature plus `|text=` + a 12-char hash of caller content tokens (stopwords, number words, and location tokens excluded).
- `run.json` schema `baansafe.rl_run.v1`: per-epoch summaries, per-episode rows, events, the final overlay, training counts, notes.
- Cascade: `source_outcomes = [deciding outcome, *prior]`, so `[0]` is always the deciding system.
- S2 modes: `live` calls Mubit only through `llm.complete` (no OpenRouter client) with pacing and 429 backoff, caches replies in `s2_cache.jsonl`; `replay` reads the cache only and a miss counts as a System 2 fallback (no invented host, no socket); `fake` replays authored truth and is for tests.
- Each live Mubit POST and each cache hit emits TraceEvent stage `mubit_chat` (model, `latency_ms`, `case_id`, notes `status=ok|http_*|cache_hit`). Live miss → real Mubit hop; hit → `status=cache_hit` `host=rl_s2_cache` `latency_ms=0`. Never logs API keys. `run.json` records `model` and a `mubit` summary; `GET /metrics` surfaces `mubit_chat` counts including `cache_hit_count`.
- Learner events: `graduate`, `recommend`, `demote`, recorded once per signature.

## Invariants

- The no-stub fallback (`missing_evidence == ["fixture_stub"]`) never cascades.
- P1 and complex outcomes (requires_human, supervisor or aid route, aid need, or a safeguarding/aid flag) never graduate — they become recommendations passed back to System 2.
- Direct System 2 routes (hard trigger or demotion) never graduate.
- The bandit never routes; it only records pick vs actual.
- `eval/out/` is gitignored. No test or run hits the network without `--s2 live`. Prefer mocked unit tests; do not run live `make rl-loop` unless Mubit keys are set.

## How to test

- `python -m eval.rl --s2 fake --epochs 3` — road-info and cold-hall graduate, quiet-grandmother and upstairs-water recommend, weak-grandfather-water demotes, aid never graduates.
- `make rl-loop-replay` (cache only, no network). `make rl-loop` only with Mubit env.
- `eval/out/` is gitignored. `make rl-snapshot` copies a run into `eval/snapshots/rl/<stamp>-<MEMORY_IMPL>/` (committed); `make rl-restore SNAPSHOT=<folder>` copies one back so replay and `/rl/run` work on a fresh clone. Two 25 Oct runs are kept there (memory empty vs memory local); see its README.
- `make rl-compare` renders those two side by side (critical under-triage 9 → 2, mean reward −0.341 → 0.189) and the "Memory off vs on" card on `/ui/training.html` reads `GET /training/compare`.
- `tests/test_rl_loop.py` (fake + mocked live/replay traces), `tests/test_rl_compare.py`, `tests/test_cascade.py`, `tests/test_overlay.py`, `tests/test_orchestrator.py`.
- `GET /rl/run` and `GET /metrics` on `make serve`.

## Common pitfalls

- Reading `source_outcomes` in the wrong order. The deciding outcome is `[0]`; priors follow.
- Treating a demoted route as a cascade. A demoted coarse signature enters at System 2 directly.
- Expecting unmatched-needs escalations to graduate. Graduated rules apply only where System 1 escalates for no needs or low confidence.
- Assuming the fake completer is a model. It replays authored truth; it measures loop plumbing, not reasoning.
- Setting `RL_OVERLAY` globally in tests. It is process state cached by mtime; unset it or pass `overlay=` explicitly.
- Treating a replay miss as a Mubit hop. It is a fallback; traces stay silent for that miss.

## Open TODO_HUMAN keys

- `modal.finetune_base_model` — the export runs but fine-tune stays blocked.
- `system1.extraction_model`, `sim.caller_model`, `sim.caller_gpu`.
