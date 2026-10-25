---
title: Testing
tags: [pytest, validate, replay, ci]
files:
  - scripts/validate.py
  - scripts/check_agents.py
  - scripts/check_owners.py
  - scripts/demo_reset.py
  - scripts/demo.py
  - .github/CODEOWNERS
  - tests/conftest.py
  - Makefile
---

## Purpose

`make test` is pytest. `make validate` checks fixtures, decisions, stub files, and these agent docs. Both must pass before a PR is merged into `main`.

## Key files

- `Makefile` — `test`, `validate`, `replay-stubs`, `eval-learning`, `sim-eval`, `latte-bench`, `serve`, `modal-deploy-*`.
- `scripts/validate.py` — decisions, Sapling stubs, `NotImplementedError` in `system2/decide.py` (System 1 and `router/merge.py` are real now), schemas, personal-data scan.
- `scripts/check_agents.py` — `AGENTS.md` line budget, topic template, index paths. Called from `validate`.
- `scripts/check_owners.py` — `make check-owners`. Changed files on this branch (`git diff --name-only origin/main...HEAD` plus the working tree) against the single-writer map in the script header: `ui/sim/sim.js` (Melanie, branches `melanie/`, `mel/`) and `llm/client.py` (Moly, `moly/`). Prints a warning per file touched from a non-owner branch; exit 0 unless `OWNERS_ARGS=--strict`. A reminder, not security. `.github/CODEOWNERS` is the GitHub side (`@melaniepreen`, `@molyleelatham`); `tests/test_check_owners.py` pins the two together.
- `scripts/demo_reset.py` — `make demo-reset` (dry run; `RESET_ARGS=--yes` applies). Local mode truncates `TRACE_PATH` and `MOCK_CORRECTIONS_PATH`, removes `S2_CACHE_RECORD_PATH`, and rewrites `MEMORY_LOCAL_PATH` keeping only `baansafe-policy` rows (re-seeding the 10 lessons when none remain); `--events` also clears `TRAINING_EVENTS_PATH`. `--hosted` does the same on the Modal volume `baansafe-demo` through `modal volume get/put/rm`. Prints before/after counts per lane. `tests/test_demo_reset.py` covers both modes (hosted with a fake CLI).
- `scripts/demo.py` — `make demo` / `make backend` / `make frontend` / `make demo-stop`: one-command quick start for the API in the hosted demo config (state under `var/demo/`; `DEMO_PORT`/`RESET`/`OPEN` knobs; `DEMO_<name>` overrides one config value, an ambient shell export does not). `tests/test_demo_quickstart.py` covers the env defaults and the shell-override note, seeding, the pid-file guard, and the port check.
- `tests/conftest.py` — deletes `MUBIT_API_KEY` and `MEMORY_LOCAL_PATH` for the session; `MEMORY_IMPL=mock`. A local-mode test sets its own tmp `MEMORY_LOCAL_PATH`.
- `pyproject.toml` — `pythonpath = ["."]`, `testpaths = ["tests"]`. Requires Python `>=3.11`.
- `tests/test_architecture.py`, `test_gateway_and_replay.py`, `test_chooser.py`, `test_system1.py`, `test_router.py`, `test_extract.py`, `test_api.py`, `test_mubit_memory.py`, `test_memory_write.py`, `test_memory_local.py`, `test_sapling.py`, `test_modal_infra.py`, `test_contracts.py`, `test_learning_eval.py`, `test_sim.py`, `test_latte.py`, `test_agents_docs.py`, `test_training_schema.py`.

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
- `EXTRACT_EVAL_SET=synthetic make extract-eval` and `EVAL_LEARNING_SET=synthetic make eval-learning` for `fixtures/synthetic`. The defaults still use the original 24 fixtures and the eight stub groups.
- `python3 scripts/check_agents.py` after editing `AGENTS.md` or `docs/agents/`.
- `make check-owners` before opening a PR. Work in a worktree per branch (`git worktree add -b <branch> ../Baan-Safe-wt/<name> origin/main`); never `git add -A` in the shared checkout.
- `make demo-reset` (then `RESET_ARGS=--yes`) before a demo run so traces and case memory start from the same point. `tests/test_demo_reset.py`, `tests/test_env_example.py`, `tests/test_check_owners.py` cover the hygiene scripts.

## Common pitfalls

- Importing `infra.modal.sapling_app` at collection time without env. The app resolves `TODO_HUMAN` on import.
- Forgetting `PYTHONPATH=.` when running a script outside Make.
- Adding a fixture with a phone number or a 13-digit id. Validate fails the file.
- Updating `AGENTS.md` past 150 lines, or adding a topic file without `index.json`.

## Open TODO_HUMAN keys

None read by the test runner. Product keys the tests still expect to be unset are listed in the topic file for that area.
