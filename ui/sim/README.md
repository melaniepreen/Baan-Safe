# Town simulation

Fixed isometric view of a synthetic Thai block during a flood. The camera stays at one angle. Drag pans, the wheel zooms, and neither one rotates the view.

PixiJS draws the world. The rest of `ui/` is static HTML, and `ui.framework` is still `TODO_HUMAN`, so this view does not pick an application framework. Pixi is only the renderer. The library is the MIT build in `vendor/` (PixiJS 8.22.0) and runs in an ordinary browser. WebGL is preferred. Pixi falls back to canvas if WebGL is missing. Nothing here needs an NVIDIA GPU.

## Run

From the repo root, with the API up:

```bash
make serve
```

Open http://127.0.0.1:8000/ui/sim/

That host also serves `GET /resources`, `GET /fixtures/{id}`, `POST /triage`, and `GET /context`. The page uses them when they answer, and still draws if they do not.

Without the API, from the repo root:

```bash
python3 -m http.server 8000
```

Open http://127.0.0.1:8000/ui/sim/ . The block renders from the JSON files. The backend log says the API is not connected. Calls need the BaanSafe server.

Regenerate the JSON after editing the layout script:

```bash
python3 ui/sim/build_town.py
```

## What is real, and what is a placeholder

`data.demo_event` is still unset. The picture is a placeholder for a Bangkok flood demo. The HDX set `eos-rs-thailand-flood-bangkok-sep-2026` is listed in `data/SOURCES.md` and was not fetched. Household `location_label` stays the fixture district (Lampang, Phrae, Nan, Phayao). `flood.json` is local metres, not that Bangkok map.

| Piece | Where it lives | Contract |
|---|---|---|
| Household on a house | `data/town.json` `buildings[].household` | `Household`. `location_label` is the fixture district. No house number. |
| Status (`clear`, `at_risk`, `flooded`, `needs_help`, `evacuated`) | `buildings[].sim_status` | Not a contract field. `BaanSafeSim.setStatus(householdId, status)` changes it in the page only. |
| Hazard | `data/flood.json` and `town.json` `hazards` | `Hazard` with `kind: flood`. Local metres, not WGS84. |
| Dispatch category on a drawn path | `town.json` `routes[].contract_route` | `Route` enum (`shelter_placement`, `rescue_coordination`). The enum is not a polyline. |
| Path geometry | `town.json` `graph`, `routes[]`, and `response_routes[]` | No path API. `routes` keeps the F06 foot path and the F10 boat path. `response_routes` is one path per call from the jetty, shelter, water desk, and school. A run may change from foot to boat where the drawn street changes mode. Lanes are extra edges flagged `lane`. |
| Boats, shelter, clinic van, water desk | placed on buildings, ids from `mocks/resources.json` | `Resource`, and `GET /resources` when the API is up. |
| Live flood flags | not drawn as this grid | `GET /context?district=…` and `GET /map/flood`. The WGS84 polygons are a different picture. |

Street names are in `data/streets.json`. Every name is marked placeholder (`จำลอง` / `PLACEHOLDER`). Replace that file to use real names. Household records do not store the street.

The phone on the left is the caller. Type a line and press Send, or press Call and speak. Call uses the microphone (`MediaRecorder`) and, when the browser has it, the Web Speech API. If `POST /stt/transcribe` answers, that text is used instead. This API does not mount `infra/modal/stt_app`. `speech_to_text.provider` is still `TODO_HUMAN`. When neither path returns words, the phone shows a stub transcript and does not invent a sentence.

`gateway.route_chooser` is still `TODO_HUMAN`, so a case that is not a fixture is not routed. The page has a **DEMO-ONLY chooser** (it is not backend policy). It maps the typed or spoken line to a fixture with a keyword rule or the nearest scripted opening, and the screen says which rule fired. The page then `POST`s `/cases` with that `fixture_id` and `POST`s `/cases/{id}/turns` with the caller's text. The stub gateway answers the fixture id. It does not read the new sentence with a live model. The reply in the phone is `next_question` when the outcome has one, otherwise the priority, route, and next action. It is labelled stub gateway, not a live operator.

`Correct this` opens when the operator presses Reject. The form fills `task` and `input_ref` from the case and the gateway decision. The operator picks `output_correct` from the closed enum for that task and types a reason. The post is `POST /cases/{case_id}/corrections` with `source` `human` and `corrected_by` `operator`. The same form is on the transcript player.

The priority comes from the call on the phone. There is no separate P1–P4 button. The stub gateway's `final_priority` lights that house and the draft rulebook picks the vehicle.

The panel on the right plays a timeline from `data/sim_events.json`. Every step is badged **simulated**. The event shape is `schema_version` `baansafe.sim_activity.v1`: `id`, `kind` (`memory`, `tool`, `system_1`, `handoff`, `system_2`, `sapling`, `router`), `text` with placeholders, `delay_ms`, `source`, and optional `when` (`rejected` or `aid`) and `fill` (`flood` or `shelter`). System 1 scores and need scores live on the scenario. The confidence threshold (default 0.75, the number in the panel) accepts the fast path when the top score is at least the threshold, and otherwise plays the handoff into the scripted System 2 lines. Where the stub gateway returned a field, the same step shows it underneath (priority, route, next action, reason, memory summaries, lot `water_m`, shelter path length).

A real stream can replace the file later. Call `BaanSafeSim.attachLiveFeed(source)` with an `EventSource` or any object that emits `step` events of the same shape. A future gateway path such as `GET /cases/{case_id}/events` (SSE) or a websocket is the place to connect. Set `source` to `gateway` on those objects. Nothing in this API emits that stream today.

Sapling's simulated line uses `supported`, `violation`, `missing`, or `unsure` only as a labelled drill. The stub gateway does not return `sapling_verdict`, and `mocks/sapling_stub` is not this household's verdict.

`data/rulebook.json` is a **DRAFT** table, pending confirmation, and it is not repo policy. The first matching row chooses the picture: a boat with a wake from the jetty (then on to the clinic or the shelter), a truck for evacuation, a van for a welfare drop, or an SMS pulse for information. The boat's return to the clinic is a walk on the existing street graph (`route_walk.js`), not a new chord. A flooded segment of a truck or van path draws a boat instead, because that edge is boat-only. Accept confirms the decision in the log. Reject stops the vehicle and opens `Correct this`.

The decision log is `localStorage` key `baansafe.sim.decision-log` (case, priority, rule, action, operator, time). Export JSON downloads it. Saved prompts are in `data/prompts.json`.

The priority text still quotes `config/priorities.yaml` and, separately, a suggestion from `research/thai-flood-management.md` that is not repo policy (`data/responses.json`).

`Play 20 calls` walks `fixtures/index.json` in order through the same case-turn path. The line on the picture runs from the call to the Mubit chip to the house. Lights are the gateway priority: P1 red, P2 amber, P3 yellow, P4 blue. `Step` sends one call. `Reset` clears the lights. F09 is the same house as F08. F07 is the school. F16 is the shelter. Flood level is the depths in `flood.json`. It rises on its own. There is no slider.

`BaanSafeSim.setStatus` still changes `sim_status` in the page only. There is no inspect panel.

## Demo script

Open http://127.0.0.1:8000/ui/sim/ with `make serve` already running. `data.demo_event` stays unset.

1. Watch the flood rise to `flood.json`. The phone's first note says this block is a placeholder, not the unfetched EOS-RS Bangkok map.
2. Open **Prompts** and tap the System 1 rice line (F02). The chooser note says it is a saved prompt. The timeline badges each step simulated. System 1 shows P3 above the threshold and **ACCEPTED**. The house lights P3. A van leaves the water desk along the drawn roads. The phone quotes the stub reason. The rulebook row `p3-welfare` highlights, and the decision log gains a row. Press **Accept**.
3. Open **Prompts** and tap the System 2 oxygen line (F10). System 1's top score is under the threshold, so the step says **REJECTED** and the handoff line plays. The gateway stub beside it is P1 rescue. A boat with a wake runs from the jetty to the house, then along the drawn streets toward the clinic. The rule is `p1-medical`.
4. Open **Prompts** and tap the Sapling rent line (F17). The route is `aid_caseworker`. The Sapling step is the dashed simulated verdict (`missing`). The stub gateway has no `sapling_verdict`. The phone says a human is required. No vehicle is dispatched. Do not treat `mocks/sapling_stub` as this household's verdict.
5. Raise the confidence threshold above 0.82 and send the rice line again. System 1 is **REJECTED** and the handoff animates, while the gateway stub underneath is still the System 1 outcome.
6. Press **Reject** on a decision. The vehicle stops and **Correct this** opens. Task and the case link are filled from the case and the gateway decision.
7. Type `Our rice is finished. Can someone bring food today?` and press the send arrow. The chooser matches F02 by the food keyword and says it is demo-only.
8. Press the green Call button, speak, then the red end-call button. The in-call screen shows a timer. The phone names Web Speech API, `POST /stt/transcribe`, or the stub transcript. Only a real transcript is sent on.
9. Open "20 scripted calls" and press Step to send the next fixture in index order. Export JSON downloads the decision log.
