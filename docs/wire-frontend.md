# Wire the frontend

24 October 2026. Plan to connect `ui/sim/` (and the transcript player) to what the API already returns. Source gaps: `HANDOVER.md` items 4–7, 11, 14, 17, 29–37. Do not edit `frontend-prototype/` unless a task names it (`docs/agents/frontend.md`).

## Problem

The town desk and Correct-this UI work, but much of what they show is local demo logic. The gateway already extracts, enriches, routes, and dispatches. The UI often ignores that and invents a parallel story.

| Surface | Path | Role |
|---|---|---|
| Town desk | `ui/sim/index.html`, `ui/sim/sim.js` | Live demo after `POST /cases` / turns |
| Correct this | `ui/correct.js` | Operator training events |
| Transcript player | `ui/player.html` | Fixture stream + Correct this |
| Static gallery | `frontend-prototype/` | Design-only; no API |

## Goals

1. What the town draws matches `RouterDecision` and case enrichment.
2. Free-text / spoken turns hit extraction (not only `fixture_id`).
3. Unused endpoints and case fields that already exist get a UI consumer where they help the demo.
4. Local demo chooser / rulebook / scripted learning text stop contradicting decided config.

Non-goals for this plan: Melanie’s caseworker view, a React/Vue app (`ui.framework` is still `TODO_HUMAN`), live STT (`speech_to_text.provider` is `TODO_HUMAN`), wiring `frontend-prototype/`.

## Already on the wire (use these)

| API / field | Today | Wire to |
|---|---|---|
| `POST /cases` with `transcript` (empty fields) | Accepted; demo posts `{ fixture_id }` only | Free-text and phone paths |
| `POST /cases/{id}/turns` → `TurnResult.decision` | Used for triage panel | Also drive vehicles and status |
| `RouterDecision.dispatches` | Never read in `sim.js` | Town vehicles / resource markers |
| `case.resources.location_context` | Set in `gateway/route.py` | Nearby hospitals, shelters, rain, freshness |
| `GET /cases/{id}` | Decision history | Turn timeline / operator desk |
| `GET /context`, `GET /resources` | Live | Context strip; stock (after ledger fix) |
| `GET /map/flood`, `GET /map/facilities` | GeoJSON served; no page | Optional map panel |
| `GET /metrics` | Latency / S1 share | Quality strip |
| `GET /policies/match`, `GET /policies/{rule_id}` | Cite rule | Decision reason footnote |
| `POST /replay` | Score fixtures | Operator “score all” control |
| Thai `name_th` / facility names | In DB / context | Labels when `lang` is `th` or `mixed` |

## Work packages

### P0 — Stop lying about the decision

1. **Post transcripts for free text.** When the operator types or the phone path has words, call `POST /cases` with `transcript` turns (and empty / omitted `fields`), not only `{ fixture_id: call.id }`. Keep fixture-id create for one-click household demos.
2. **Render `dispatches`.** On each `TurnResult`, map `decision.dispatches[]` (`need`, `resource_kind`, `resource_id`, `status`) onto town units. Prefer backend `resource_id` over `ui/sim/data/rulebook.json` priority → vehicle.
3. **Show `location_context`.** Surface nearest hospitals/shelters and rain/forecast from `case.resources.location_context` in the desk panel. Do not invent distances.
4. **Fix stale copy.** Remove or update strings that still say `gateway.route_chooser` and `system2.orchestrator_model` are `TODO_HUMAN`. Align `sim_events.json` `learning.promote_after` with the real story (correction graduation vs `RL_OVERLAY`); pick one narrative for the demo.

### P1 — Align demo helpers with the gateway

5. **Demote the page-local chooser.** Label it demo-only or remove keyword → fixture mapping once free-text create works. Do not present it as `route_chooser`.
6. **Rulebook as overlay, not authority.** If the table stays for teaching, mark rows that disagree with `dispatches`. Vehicle motion should follow provisional dispatches.
7. **Geography.** Either set `data.demo_event` (e.g. Hat Yai / Songkhla so GISTDA floods light up) or move the town basemap toward fixture provinces (Lampang, Phrae, Nan, Phayao). Sukhumvit + northern fixtures will keep enrichment looking empty.
8. **Stock.** Prefer ledger-aware availability once an endpoint exposes holds; until then, do not treat `GET /resources` as live stock after a dispatch.

### P2 — Endpoints and data the UI never calls

9. **Context strip:** `GET /context?district=…` when the case has a location but enrichment was off at create.
10. **History:** `GET /cases/{id}` for multi-turn decision history next to Correct this.
11. **Metrics:** `GET /metrics` for a small latency / % System 1 readout (hackathon track).
12. **Policy cite:** after a decision, optional `GET /policies/match` or `GET /policies/{rule_id}` under the reason line.
13. **Replay control:** button → `POST /replay` for fixture scoreboard (operator / judge).
14. **Map panel (optional):** WGS84 pins from `admin_districts` centres + `GET /map/flood` / `GET /map/facilities`, filtered by province. Not a replacement for the local-metre town unless product chooses one map.

### P3 — Backend gaps the UI cannot fake

These block honest UI; fix in API/router before or with the UI:

- Confirm / cancel / close dispatch (no endpoint; holds clear only on re-decide).
- `GET /resources` ignoring the ledger.
- Hosted Modal `STUB_ENV` (`S1_IMPL=stub`, `ENRICH_IMPL=off`) if the public demo should show real System 1.
- Enrichment `districts`-only match (fall back to `admin_districts`) so Hat Yai and most gazetteer points get facilities and flags.

## Files to touch

| Change | Likely files |
|---|---|
| Create / turn payload and dispatch draw | `ui/sim/sim.js`, maybe `ui/sim/approval.js`, `ui/sim/route_walk.js` |
| Desk copy and panels | `ui/sim/index.html`, `ui/sim/sim.css` |
| Scripted learning text | `ui/sim/data/sim_events.json` |
| Vehicle rules demotion | `ui/sim/data/rulebook.json` (or stop reading it for motion) |
| Correct this unchanged contract | `ui/correct.js` (already posts v1; keep enums aligned) |
| Player optional context | `ui/player.html` |
| Tests | extend UI contract tests if any assert payload shape; do not require a browser in `make test` |

Leave alone unless named: `frontend-prototype/**`, trained-model loading, `countries/` loader.

## Acceptance checks

- Typing a fixture-like English line without `fixture_id` still produces needs / route via extraction (or a clear escalate), visible in the desk.
- After a turn, on-screen vehicle / shelter ids match `decision.dispatches` when `resource_id` is set.
- `location_context` hospitals or shelters appear for a fixture with a resolvable district (e.g. F10 pattern).
- No UI string claims `route_chooser` or `orchestrator_model` is undecided.
- `make test` and `make validate` stay green; `frontend-prototype/` diff empty.

## Suggested order

1. Transcript create path + drop stale TODO copy.  
2. Dispatches → town.  
3. `location_context` panel.  
4. Demote rulebook / chooser / `sim_events` learning story.  
5. Geography or `demo_event` so enrichment is visible.  
6. Metrics / history / policies / replay as thin panels.  
7. Map GeoJSON only if the basemap decision is settled.

## References

- `HANDOVER.md` — Gaps 4–7, 11, 14, 17, 29–37  
- `docs/agents/frontend.md` — UI invariants  
- `docs/agents/decision-router.md` — `merge()` and dispatches  
- `docs/agents/data-sources.md` — enrichment flags and snapshots  
- `BaanSafe_Revised_Architecture.md` — routing walk-through  
