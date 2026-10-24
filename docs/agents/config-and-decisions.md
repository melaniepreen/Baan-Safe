---
title: Config and decisions
tags: [config, decisions, todo-human, yaml]
files:
  - config/decisions.yaml
  - config/settings.py
  - scripts/validate.py
---

## Purpose

Product choices live in `config/decisions.yaml`. Readers fail loudly while a value is `TODO_HUMAN`. Humans change values. Code does not invent them.

## Key files

- `config/decisions.yaml` — every leaf. Comments are not values.
- `config/settings.py` — `UNSET`, `decisions()` (cached), `require_decision`, `unset_decisions`, `DecisionRequired`.
- `scripts/validate.py` — `DECIDED` allowlist. Any other leaf must be the string `TODO_HUMAN`.
- `config/routing.yaml` — harness `mode: exclusive`. The live chooser is `gateway.route_chooser` (`field precheck`, implemented in `gateway/chooser.py`).
- `config/priorities.yaml`, `config/routes.yaml`, `config/escalation.yaml`, `config/ingest.yaml`.
- `config/envfile.py` — loads `.env`. Do not print it.

## Interfaces/contracts

- `require_decision(path)` returns the value or raises `DecisionRequired`.
- `unset_decisions(paths)` returns the paths that are missing, `None`, `""`, or `TODO_HUMAN`.
- Allowlisted today (`DECIDED`, eight leaves): `system2.use_banyan_sapling` `true`, `system2.sapling_scope` `aid_eligibility,denial`, `sapling.client` `stub`, `system2.hosting` `openrouter via mubit gateway`, `llm.provider_route` `mubit`, `gateway.route_chooser` `field precheck`, `system1.extraction_method` `rules-only`, `correction_loop.graduation_threshold` `2`.
- A new decided value needs the yaml leaf and a matching `DECIDED` entry. Validate fails if they differ.

## Invariants

- Do not put a model id, GPU name, price, or threshold into yaml from a research note.
- `decisions()` is `lru_cache`d. Tests that change the file in-process must clear the cache. Prefer a new process.
- `modal.*` stays `TODO_HUMAN` in git even when a deploy exports the same name as an environment variable.
- Routing mode stays `exclusive`. Validate checks the string `mode: exclusive`.

## How to test

- `make validate`
- `tests/test_architecture.py` — `complete` still needs `system2.orchestrator_model`; OpenAI client registers the Mubit compat prefix.
- `tests/test_modal_infra.py` — `resolve` refuses `TODO_HUMAN`.

## Common pitfalls

- Setting a leaf to a real value and forgetting `DECIDED`. Validate rejects it.
- Setting `DECIDED` without changing yaml. Validate rejects the mismatch.
- Caching a decision in a new module-level global. Read it through `settings.py` at call time.
- Using `system2.hosting` as a URL. The value is the words `openrouter via mubit gateway`, not a host.

## Open TODO_HUMAN keys

All leaves except the eight in `DECIDED`. The groups are `system1`, `system2` (model id and `max_latency_ms`), `sapling` (except `client`), `gateway`, `memory`, `llm` (`token_price_usd`), `speech_to_text`, `ui`, `data`, `policies` (`authoritative_set`), `correction_loop`, `learning_eval`, `latte_bench`, `sim` (`caller_model`, `caller_gpu`), `modal`.
