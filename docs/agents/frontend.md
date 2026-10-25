---
title: Frontend
tags: [ui, frontend-prototype, transcript, correction]
files:
  - ui/player.html
  - ui/correct.js
  - ui/transcript_player.py
  - frontend-prototype/README.md
---

## Purpose

The operator UI is the transcript player and the town desk. `Correct this` sends a v1 correction. `frontend-prototype/` is a static HTML gallery. Agents do not edit the prototype unless the task says so.

## Key files

- `ui/player.html` — plays `GET /fixtures/{id}/stream`, then shows Correct this.
- `ui/correct.js` — fills `task` and `input_ref`. The operator picks `output_correct` and types `reason`.
- `ui/sim/index.html` — same form after gateway triage on a household.
- `ui/training.html`, `ui/training.js` — training page: reads `GET /training`, draws Mubit traffic cards, the fine-tune versions table with an inline SVG loss chart, RL epochs, and event counts. Plain JS. Topic: `docs/agents/training-surface.md`.
- `ui/transcript_player.py` — `python -m ui.transcript_player F01 --pace 0`. Fixture text only. Owner: Moly.
- `frontend-prototype/README.md` — gallery `index.html`, variants `v0-dark/` through `v5/`.
- `contracts/training.py` — closed labels. The form does not define a second enum.

## Interfaces/contracts

- Task is `s1_triage` for System 1, `sapling_verdict` for a System 2 aid or denial case, and `s2_action` otherwise.
- `input_ref` is `case_id`, turn ids, `lang` (`th`, `en`, or `mixed`), policy ids, and `memory_ref`.
- The post is `POST /cases/{case_id}/corrections` with `source` `human` and `corrected_by` `operator`.
- `ui.framework` is `TODO_HUMAN`. There is no React or Vue app in `ui/`.
- Prototype pages are simulated. Do not copy a baht figure from them into `system1/` or `config/`.

## Invariants

- Do not edit `frontend-prototype/` unless the task names it.
- The prototype does not call a model. Do not wire `fetch` to OpenRouter or Mubit from those HTML files.
- The form does not ask the operator for `task` or `input_ref`.
- The label lists in `ui/correct.js` match `S1Label`, `S2Action`, and `SaplingVerdict`.
- Speech-to-text is not implemented. `speech_to_text.provider` is `TODO_HUMAN`.
- Melanie's caseworker view is not built (`OWNERSHIP.md`).

## How to test

- `python -m ui.transcript_player F01 --pace 0` prints the fixture turns.
- `tests/test_correct_ui.py` checks the enums, the v1 body, and that the pages only name the label and the reason.
- `make test` does not render the prototype.

## Common pitfalls

- Sending a priority or a route as an s1 label. Those are not closed labels.
- Editing `frontend-prototype/` while changing the player. The gallery is a separate static tree.
- Adding a framework to `ui/` while `ui.framework` is unset.

## Open TODO_HUMAN keys

- `ui.framework`
- `speech_to_text.provider`
