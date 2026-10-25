---
title: System 2 and Sapling
tags: [system2, nemotron, sapling, verifier, openrouter]
files:
  - system2/decide.py
  - system2/orchestrator.py
  - system2/sapling.py
  - system2/sapling_client.py
---

## Purpose

Nemotron reasons. Sapling then checks System 2 aid-eligibility and denial claims. The Decision Router sees the result. `system2.orchestrator_model` and `system2.max_latency_ms` are decided, so `orchestrate` calls the model through `llm.complete`.

## Key files

- `system2/decide.py` — `orchestrate(case, handoff, recommendation)`, then `verify_before_router`. Owner: Melanie.
- `system2/orchestrator.py` — prompts Nemotron, parses one JSON object into `reasoned_recommendation`, falls back to a safe `system2_unavailable` outcome on timeout, HTTP error, empty content, or parse/enum failure. The fallback reason names the HTTP status (429 is marked rate limited). The fallback is P1 when the case has a life-safety trigger — `medical` or `oxygen_dependent` cite `NIEMS-ANNOUNCEMENT-2554` (Red: life threat to breathing, circulation, or the nervous system); `need:rescue` or `immobile` cite the P1 definition in `config/priorities.yaml`, because the announcement assigns no colour to being trapped — and P2 otherwise. `use_completer(fn)` swaps the model call for tests and the RL loop. The call sends `reasoning={"enabled": false}` and `max_tokens=700`: the model otherwise spends its whole budget on `<think>`.
- `system2/cache.py` — `S2_IMPL=cache`: exact-key replay for the demo. Key = sha256 over model id + full message list (same as the RL loop's `_cache_key`), so memory context and prompt must match byte for byte; nothing fuzzy. Reads `S2_CACHE_PATH` (default `fixtures/s2_cache/demo.jsonl`, committed, 158 replies for the fixture + synthetic set with `MEMORY_IMPL=mock`) then `S2_CACHE_RECORD_PATH` (optional; misses answered by Mubit are appended). `S2_CACHE_KEY=exact` (default) hashes the messages as sent; `case` drops `case_id`, `memory`, and `resources` from the user payload first, which is what a long-running server needs (random ids, store grows per case, ledger moves) and is what the Modal gateway sets; hits under it are traced `host=s2_cache/case`. A hit emits `mubit_chat host=s2_cache status=cache_hit` and opens no socket. A miss with credentials is one normal Mubit call; without credentials it raises `ValueError`, so the orchestrator falls back to `system2_unavailable`. `use_completer` still wins over cache mode. `gateway/route.py` treats `cache` like `real` (`_S2_LIVE`). The Modal gateway honours a deploy-time `S2_IMPL=cache` and sets `S2_CACHE_RECORD_PATH=/data/s2_cache.jsonl`; `/hosting` reports `backends: cache`. Record after memory is seeded: `make record-s2-cache` (fixtures) or run the demo script once on the hosted URL so every scripted turn is a hit.
- `scripts/record_s2_cache.py` — `make record-s2-cache` runs every fixture (and `--synthetic`) through the gateway in cache mode with the committed file as record path. Needs `.env`; re-runs only fill misses.
- `system2/sapling.py` — scope, verdict application.
- `system2/sapling_client.py` — stub client. `SAPLING_IMPL=live` refuses before any socket.
- `mocks/sapling_stub/` — `S01`–`S05`.
- `system2/aid_exceptions.py` — separate stub. See `docs/agents/policies-api.md`.

## Interfaces/contracts

- `decide(case, handoff=None, recommendation=None) -> Outcome`. The handoff is the System 1 outcome on a cascade; the recommendation is a learned rule System 2 may weigh. `NotImplementedError` from `orchestrate` is re-raised; Sapling does not run in that case.
- Scope is `system2.sapling_scope`: `aid_eligibility,denial`. System 1 is skipped.
- Verdicts: `supported` leaves the action. `violation` sets `requires_human` and route `supervisor_escalation`. `unsure`, `missing`, `contradicted` set `requires_human`, keep the route, and append `sapling_<verdict>` to `missing_evidence`.
- Checkpoint labels: `insufficient_information` → `missing`, `inconsistent_context` → `contradicted`.
- Input cap 16,384 tokens. Over-limit and empty inputs become an unsure handoff. The client does not truncate.
- Published checkpoint id in code: `MubitLabs/banyan-sapling`. `sapling.model_id` in yaml is still unset.

## Invariants

- `system2.hosting` is `openrouter via mubit gateway`. The orchestrator does not call OpenRouter; `llm.complete` refuses non-Mubit hosts and never prints the key. Hard post-rules force `requires_human` on a `safeguarding` flag, an aid need, or aid flags.
- `system2.use_banyan_sapling` is `true`. `sapling.client` is `stub`. Tests do not load a GPU.
- `scripts/validate.py` rejects an `Outcome(` constructor in `system2/decide.py`.
- Unknown policy/evidence/claim triples from the stub client are `unsure`, not `supported`.
- Thai text refuses while `sapling.thai_handling` is unset. Do not guess translate-versus-send.

## How to test

- `make test` — `tests/test_sapling.py`, `tests/test_gateway_and_replay.py` (System 2 raise names Melanie), `tests/test_s2_cache.py` (hit without socket, miss fallback, record path, Modal env).
- `make replay-stubs` — includes `S01`–`S05`.
- `make validate` — five stub files, every verdict, both checks.

## Common pitfalls

- Running Sapling inside `orchestrate`. `decide` runs it after an outcome exists.
- Setting `sapling.model_id` in git. The Modal app stays refused until a human exports `SAPLING_MODEL_ID`.
- Treating `Outcome.escalate` as the Sapling handoff. That field means System 1 to System 2. Sapling sets `requires_human`.

## Open TODO_HUMAN keys

- `sapling.hosting`, `sapling.gpu`, `sapling.thai_handling`, `sapling.model_id`
