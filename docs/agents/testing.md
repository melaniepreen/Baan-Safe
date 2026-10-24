---
title: Testing
tags: [pytest, validate, replay, ci]
files:
  - scripts/validate.py
  - scripts/check_agents.py
  - tests/conftest.py
  - Makefile
---

## Purpose

`make test` is pytest. `make validate` checks fixtures, decisions, stub files, and these agent docs. Both must pass before a push to `main`.

## Key files

- `Makefile` — `test`, `validate`, `replay-stubs`, `eval-learning`, `sim-eval`, `latte-bench`, `serve`, `modal-deploy-*`.
- `scripts/validate.py` — decisions, Sapling stubs, `NotImplementedError` in the three stub entry points, schemas, personal-data scan.
- `scripts/check_agents.py` — `AGENTS.md` line budget, topic template, index paths. Called from `validate`.
- `tests/conftest.py` — deletes `MUBIT_API_KEY` for the session.
- `pyproject.toml` — `pythonpath = ["."]`, `testpaths = ["tests"]`. Requires Python `>=3.11`.
- `tests/test_architecture.py`, `test_gateway_and_replay.py`, `test_api.py`, `test_sapling.py`, `test_modal_infra.py`, `test_contracts.py`, `test_learning_eval.py`, `test_sim.py`, `test_latte.py`, `test_agents_docs.py`.

## Interfaces/contracts

- Pytest is `python3 -m pytest -q` with `PYTHONPATH=.`.
- Validate prints `validate ok: N fixtures` or a problem list and exit 1.
- `scripts/check_agents.py` prints `agent docs ok` or exits 1. Budget: `AGENTS.md` at most 150 lines.
- Topic files under `docs/agents/` (except `INDEX.md`) must be in `docs/agents/index.json` and contain the seven `##` sections.

## Invariants

- Do not assert on a secret value by echoing it. Tests use `mbt_should_not_appear` and check it is absent from the exception text.
- Do not skip `make validate` because pytest passed. The personal-data scan and `DECIDED` check are not all in pytest.
- `frontend-prototype/` is not part of `make test`. Leave it unless the task says so.
- Replay success is label match on stub files, not a live model score.

## How to test

- `make test`
- `make validate`
- `make replay-stubs` when stub labels change.
- `python3 scripts/check_agents.py` after editing `AGENTS.md` or `docs/agents/`.

## Common pitfalls

- Importing `infra.modal.sapling_app` at collection time without env. The app resolves `TODO_HUMAN` on import.
- Forgetting `PYTHONPATH=.` when running a script outside Make.
- Adding a fixture with a phone number or a 13-digit id. Validate fails the file.
- Updating `AGENTS.md` past 150 lines, or adding a topic file without `index.json`.

## Open TODO_HUMAN keys

None read by the test runner. Product keys the tests still expect to be unset are listed in the topic file for that area.
