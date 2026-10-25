---
title: Frontend
tags: [ui, frontend-prototype, transcript, correction]
files:
  - ui/player.html
  - ui/correct.js
  - ui/transcript_player.py
  - ui/training_polish.js
  - ui/sim/hosting_banner.js
  - ui/sim/check_hosting_banner.mjs
  - ui/sim/subtitle.js
  - ui/sim/check_subtitle.mjs
  - frontend-prototype/README.md
---

## Purpose

The operator UI is the transcript player and the town desk. `Correct this` sends a v1 correction. `frontend-prototype/` is a static HTML gallery. Agents do not edit the prototype unless the task says so.

## Key files

- `ui/player.html` — plays `GET /fixtures/{id}/stream`, then shows Correct this.
- `ui/correct.js` — fills `task` and `input_ref`. The operator picks `output_correct` and types `reason`.
- `ui/sim/index.html` — same form after gateway triage on a household.
- `ui/training.html`, `ui/training.js` — training page: reads `GET /training`, draws Mubit traffic cards, the fine-tune versions table with an inline SVG loss chart, RL epochs, and event counts. Plain JS. Topic: `docs/agents/training-surface.md`.
- `ui/training_polish.js`, `ui/training_polish.css` — loaded after `training.js` by one `<script>` and one `<link>` in `training.html`. Fetches `GET /training` once more (`training.js` keeps its copy private), adds a `Hub` column to the versions table (`s1_triage` → `baansafe/baansafe-s1-triage-setfit`; task `sft` or a role containing `s2` → `baansafe/baansafe-s2-nemotron-nano-4b-lora`; plain anchors, nothing fetched from the Hub), and draws `#heldout-labels` under the loss chart: the per-label `support`, `precision`, `recall` table for the newest `s1_triage` version with `metrics.heldout.per_label`, sorted by support, captioned `<rows> held-out synthetic rows, accuracy <accuracy>` from the data. A null precision stays `—`.
- `ui/sim/hosting_banner.js`, `ui/sim/hosting_banner.css` — the 24px strip at the top of the town page (`#hosting-banner`, first child of `<body>`). On load it reads `GET /hosting` (Modal gateway) and `GET /health` (every build) and prints `System 2 (Nemotron): live via Mubit | replaying saved answers, live via Mubit on new calls | sample answers, no model call · Case memory: on (BaanSafe store) | sample files | off (Mubit memory API unavailable) · Inference API: ready | ready (saved answers) | sample answers | not connected | checking… · Read API: ready`. Tones follow `modelpath.js`: `live` green, `cache` blue, `muted` for stub or no API, `error` red when `MEMORY_IMPL=mubit` or `/health` `memory.dormant` is true, with the `/health` warning text on the line. `hostingLabel(hosting, health)` is pure and exported; `node ui/sim/check_hosting_banner.mjs` runs it. The CSS nudges `.wordmark`, `#phone`, and `#side-stack` down by the strip height; `sim.css` and `sim.js` are untouched. Technical `note` bubbles in the phone log are hidden by default; `?notes=1` on the URL shows them. `ui/sim/subtitle.js` — `chooserSubtitle(health)`: the plain-language `#chooser-note` under the phone number, built from `GET /health` impl/memory; pure, `FALLBACK` when the fetch fails.
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
- `node ui/sim/check_hosting_banner.mjs` runs the banner label builder against `/hosting` and `/health` shapes (cache, live, stub, dormant, health-only, offline). `node ui/sim/check_modelpath.mjs` covers the `CACHE HIT · replayed` badge and the `s2_cache/case` host on a replayed hop.
- `make test` does not render the prototype.

## Common pitfalls

- Sending a priority or a route as an s1 label. Those are not closed labels.
- Editing `frontend-prototype/` while changing the player. The gallery is a separate static tree.
- Adding a framework to `ui/` while `ui.framework` is unset.
- Hardcoding the held-out caption or the Hub repo state. The rows and accuracy come from `metrics.heldout`; the link text says `Hub`; the two repos are public since 25 Oct, and the page never fetches them.
- Putting town-page banner styles in `sim.css`, or training-page polish in `training.js`. Those files have single writers; the polish lives in the `*_polish.*` and `hosting_banner.*` files.

## Open TODO_HUMAN keys

- `ui.framework`
- `speech_to_text.provider`
