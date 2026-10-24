---
title: Frontend
tags: [ui, frontend-prototype, transcript]
files:
  - ui/transcript_player.py
  - frontend-prototype/README.md
---

## Purpose

The product UI in this repo is a transcript player. `frontend-prototype/` is a static HTML gallery. Agents do not edit the prototype unless the task says so.

## Key files

- `ui/transcript_player.py` — `python -m ui.transcript_player F01 --pace 0`. Plays a fixture stream. Owner: Moly.
- `frontend-prototype/README.md` — gallery `index.html`, variants `v0-dark/` through `v5/`.
- `frontend-prototype/v1/`, `v2/`, `v3/` — static diagrams. They do not call the API or Sapling.
- `contracts/schemas/` — JSON Schemas exported for a future TypeScript UI. Shapes only.

## Interfaces/contracts

- The player reads `fixtures` via `fixtures.load.load_fixture`. It does not call `/triage`.
- `ui.framework` is `TODO_HUMAN`. There is no React or Vue app in `ui/`.
- Prototype pages are simulated: budgets, callers, and costs on those pages are not repo data. Do not copy a baht figure from them into `system1/` or `config/`.

## Invariants

- Do not edit `frontend-prototype/` unless the task names it.
- The prototype does not call a model. Do not wire `fetch` to OpenRouter or Mubit from those HTML files as a drive-by.
- Speech-to-text is not implemented. `speech_to_text.provider` is `TODO_HUMAN`. The player prints scripted fixture text.
- Melanie's caseworker view is not built (`OWNERSHIP.md`).

## How to test

- `python -m ui.transcript_player F01 --pace 0` prints the fixture turns.
- `make test` does not render the prototype. There is no browser check in pytest for `frontend-prototype/`.
- If a task does change the prototype, say so in the commit. Do not treat a screenshot as a test of the API.

## Common pitfalls

- "Fixing" the prototype SVG while changing the gateway. The gallery is a separate static tree.
- Treating the prototype's DDPM reserve line as an ingest source. DDPM is not a client. See `docs/agents/data-ingest.md`.
- Adding a framework to `ui/` while `ui.framework` is unset.

## Open TODO_HUMAN keys

- `ui.framework`
- `speech_to_text.provider`
