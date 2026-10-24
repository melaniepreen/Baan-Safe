# Handover

24 October 2026, evening. `main` is at `385c42a` plus the Cursor Agent's PRD refreshes. `make test` is 232 passed, 1 skipped (`tests/test_synthetic_calls.py` needs the `laya` module). `make validate` is ok.

## What landed

- `9da21c7` merges two parallel designs that both used `correction_loop.graduation_threshold`.
  - `correction_loop.graduation_threshold: 2` keeps its original meaning: System 2 to a System 1 rule. Only the offline RL loop reads it (`eval/rl/`, `gateway/overlay.py`). The overlay is live only when `RL_OVERLAY` names a file.
  - `correction_loop.escalation_threshold: 2` is new. `gateway/graduation.py` reads it. Two human `s1_triage` corrections on one pattern tag it `complex_situation` and send it to System 2. It never moves a pattern into System 1.
  - `complex_situation` forces a System 2 entry, so a human escalation always wins over a learned System 1 rule.
  - `routing.yaml` is `mode: cascade`. A System 1 escalate hands the same turn to System 2. The no-stub fallback never cascades.
- `edd64d0`: the System 2 fallback reason names the HTTP status (`HTTPStatusError 429 (rate limited)`). `gateway/graduation.py` reuses its result while the event log is unchanged, so a turn no longer re-reads the whole log.
- `385c42a`: a System 2 outage is P1 when the case has a life-safety trigger, and P2 otherwise.
  - `medical` and `oxygen_dependent` cite `NIEMS-ANNOUNCEMENT-2554` (Red: a life threat to breathing, circulation, or the nervous system).
  - `need:rescue` and `immobile` cite the P1 definition in `config/priorities.yaml`. The B.E. 2554 announcement assigns no colour to being trapped (`policies/system1_labels.yaml`).
  - During an outage, F12 and F14 (P2 when System 2 answers) show as P1.
- `385c42a`: English district names match bare when they have two or more words that are not all common English. "Mae Mo" and "Khlong Toei" match. "Than To" and "Hot" do not. `DISTRICT_ALIASES` in `system1/extract.py` maps caller spellings to the HDX names, including `Watthana` to `Vadhana` for the demo town. A name in two provinces stays at confidence 0.6. No location changed across the 240 synthetic calls.
- Country-pack line citations into `system1/extract.py`, `gateway/route.py`, `router/merge.py`, `system1/decide.py`, `config/decisions.yaml`, and `ui/sim/sim.js` were repointed. Several already pointed at blank lines.
- PRs #2 and #4–#7 are merged. The four `cursor/*` branches were checked against `main` and deleted. Only `main` remains.

## Live System 2

Live Nemotron is wired, but the free OpenRouter tier is used up for today: 50 requests a day, reset at 00:00 UTC. Every live call returns 429, and `orchestrate` falls back to a `system2_unavailable` escalation. `make rl-loop` spends that quota. `make rl-loop-replay` replays the cached replies and does not call the model. Adding OpenRouter credits raises the limit. That is a spending decision for a person.

## Needs a person

1. **Confirm the decisions written into config as decided.** They are `routing.yaml` `mode: cascade`, `system2.orchestrator_model` `nvidia/nemotron-3.5-lightning:free`, and `system2.max_latency_ms` 10000. An agent set them, and AGENTS.md invariant 2 says humans set decisions.
2. **Dispatch fallback.** With no district match, `router/merge.py` takes the first unit, which is an OpenStreetMap unit such as `shelter-way-{osm_id}`. The town draws only the four fictional units in `mocks/resources.json`, so that dispatch has no place on screen. Recommendation: the no-match fallback prefers the fictional units. Not done.
3. **`G01`–`G04` labels say System 1.** `rescue` is a `needs_any` trigger, so the precheck sends them to System 2. Neither graduation path changes that. Relabel them, or change their need.
4. **Phone text never reaches extract.** `runPlaceCall` posts `fixture_id`, so the spoken sentence is not extracted. PRD open item.

## Housekeeping

- Two local stashes (`rl-loop-wip-before-rebase`, `wip-pre-rl-handoff`) are redundant. Their files are on `main`. Drop them with `git stash drop` twice. An agent's drop was blocked as irreversible.
- `.vscode/settings.json` is untracked and personal. It is not committed.
- The Cursor Agent refreshes `docs/PRD.md` after pushes, at most every 30 minutes. Expect to rebase before a push.
- Two Devin sessions were still open in this folder. Pull before using them.
- The API was restarted on port 8000 from `385c42a` (`make serve`). Open http://127.0.0.1:8000/ui/sim/
