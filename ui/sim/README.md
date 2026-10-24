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
| Boats, shelter, clinic van, water desk | placed on buildings, ids from `mocks/resources.json` | `Resource`. `GET /resources` adds public shelters and hospitals from the place snapshot. The drawn mock ids stay on the block. |
| Live flood flags | not drawn as this grid | `GET /context?district=…` and `GET /map/flood`. The WGS84 polygons are a different picture. |

Street names are in `data/streets.json`. Every name is marked placeholder (`จำลอง` / `PLACEHOLDER`). Replace that file to use real names. Household records do not store the street. The school, the cancer hospital, the disaster-prevention post, and one temple on the block use public OpenStreetMap names from `data/places.json` (Lampang). The blue temple and the north hall stay the invented fixture landmarks.

The phone on the left is the caller. Type a line and press Send, or press Call and speak. Call uses the microphone (`MediaRecorder`) and, when the browser has it, the Web Speech API. If `POST /stt/transcribe` answers, that text is used instead. This API does not mount `infra/modal/stt_app`. `speech_to_text.provider` is still `TODO_HUMAN`. When neither path returns words, the phone shows a stub transcript and does not invent a sentence.

`gateway.route_chooser` is still `TODO_HUMAN`, so a case that is not a fixture is not routed. The page has a **DEMO-ONLY chooser** (it is not backend policy). It maps the typed or spoken line to a fixture with a keyword rule or the nearest scripted opening, and the screen says which rule fired. The page then `POST`s `/cases` with that `fixture_id` and `POST`s `/cases/{id}/turns` with the caller's text. The stub gateway answers the fixture id. It does not read the new sentence with a live model. The phone answers from `data/replies.json`: a short scripted operator line in English, with Thai under it when the template has a line. A question from the stub outcome is asked in the same sentence, and a human-required case adds that a colleague will confirm it. A separate note says the reply is scripted, not a live operator. Priority, route, and next action stay in the backend feed.

`Correct this` opens when the operator presses Reject. The form fills `task` and `input_ref` from the case and the gateway decision. The operator picks `output_correct` from the closed enum for that task and types a reason. The post is `POST /cases/{case_id}/corrections` with `source` `human` and `corrected_by` `operator`. The same form is on the transcript player.

The priority comes from the call on the phone. There is no separate P1–P4 button. The stub gateway's `final_priority` lights that house and the draft rulebook picks the vehicle.

The right-hand column holds a small block map above the backend feed. The map does not sit on the town. The feed plays cards from `data/sim_events.json`. Every card is badged **simulated**, with an icon and a colour for Mubit, a tool, System 1, the handoff, System 2 (Nemotron), Sapling, the decision router, or dispatch. The headline is plain English. Technical fields sit in a collapsed detail. A progress line and a gateway priority badge sit at the top. The event shape is `schema_version` `baansafe.sim_activity.v1`: `id`, `kind` (`memory`, `tool`, `system_1`, `handoff`, `system_2`, `sapling`, `router`), `text` with placeholders, `delay_ms`, `source`, and optional `when` (`rejected` or `aid`) and `fill` (`flood` or `shelter`). System 1 scores and need scores live on the scenario. The confidence threshold (default 0.75, the number in the panel) accepts the fast path when the adjusted top score is at least the threshold, and otherwise plays the handoff into the scripted System 2 lines.

Each scenario has a `theme`. Repeating a theme is simulated pattern memory (`localStorage` key `baansafe.sim.pattern-memory`, also listed in the panel). The first time a low-confidence theme appears, System 1 rejects it and System 2 takes it. Each consistent repeat raises that theme's score. After `learning.promote_after` times (3), the feed says the fast path can take it. Life-safety themes (`life_safety: true`, including trapped-oxygen and an unaccompanied child) stay with System 2 until the operator presses Accept; the next repeat of that theme can then take the fast path. Aid themes (`learns: false`) are remembered and stay with System 2 and Sapling. A changed gateway priority starts the count again. Reset patterns clears that memory. Reset on the phone does not.

A real stream can replace the file later. Call `BaanSafeSim.attachLiveFeed(source)` with an `EventSource` or any object that emits `step` events of the same shape. A future gateway path such as `GET /cases/{case_id}/events` (SSE) or a websocket is the place to connect. Set `source` to `gateway` on those objects. Nothing in this API emits that stream today.

Sapling's simulated line uses `supported`, `violation`, `missing`, or `unsure` only as a labelled drill. The stub gateway does not return `sapling_verdict`, and `mocks/sapling_stub` is not this household's verdict.

`data/rulebook.json` is a **DRAFT** table, pending confirmation, and it is not repo policy. The first matching row chooses the picture: a boat with a wake from the jetty (then on to the clinic or the shelter), a truck for evacuation, a van for a welfare drop, or an SMS pulse for information. The boat's return to the clinic is a walk on the existing street graph (`route_walk.js`), not a new chord. A flooded segment of a truck or van path draws a boat instead, because that edge is boat-only. Accept confirms the decision in the log. Reject stops the vehicle and opens `Correct this`.

The decision log stays on screen under `localStorage` key `baansafe.sim.decision-log` (case, priority, rule, action, operator, time). Clear log empties it. There is no export button. Saved prompts are in `data/prompts.json`. The boat, truck, and van lines in the phone use `eta_min` from the matching draft rule.

The priority text still quotes `config/priorities.yaml` and, separately, a suggestion from `research/thai-flood-management.md` that is not repo policy (`data/responses.json`).

`Play 20 calls` walks `fixtures/index.json` in order through the same case-turn path. The line on the picture runs from the call to the Mubit chip to the house. Lights are the gateway priority: P1 red, P2 amber, P3 yellow, P4 blue. `Step` sends one call. `Reset` clears the lights. F09 is the same house as F08. F07 is the school. F16 is the shelter. Flood level is the depths in `flood.json`. It rises on its own. There is no slider.

`BaanSafeSim.setStatus` still changes `sim_status` in the page only. There is no inspect panel.

## Demo script

Open http://127.0.0.1:8000/ui/sim/ with `make serve` already running. `data.demo_event` stays unset.

1. Watch the flood rise to `flood.json`. The phone's first note says this block is a placeholder, not the unfetched EOS-RS Bangkok map.
2. Open **Prompts** and tap the System 1 rice line (F02). The chooser note says it is a saved prompt. The cards badge each step simulated. System 1 shows P3 above the threshold and **ACCEPTED**. The house lights P3. A van leaves the water desk along the drawn roads. The phone says a welfare van is bringing food and that the reply is scripted. The rulebook row `p3-welfare` highlights, and the decision log gains a row. Press **Accept**.
3. Open **Prompts** and tap the System 2 oxygen line (F10). System 1's top score is under the threshold, so the card says **REJECTED** and the handoff plays. The feed says this life-safety call stays with System 2 until an operator confirms. The phone asks whether the water has reached the doorway, then says a rescue boat should arrive in about 12 minutes. A boat with a wake runs from the jetty to the house, then along the drawn streets toward the clinic. The rule is `p1-medical`. The pattern row says it needs confirm.
4. Open **Prompts** and tap the Sapling rent line (F17). The route is `aid_caseworker`. The Sapling card is the simulated verdict (`missing`). The stub gateway has no `sapling_verdict`. The phone talks about a payment and a colleague, not a vehicle. No vehicle is dispatched. Do not treat `mocks/sapling_stub` as this household's verdict. Repeating it does not hand the fast path the payment.
5. Raise the confidence threshold above 0.82 and send the rice line again. System 1 is **REJECTED** and the handoff animates, while the gateway priority badge is still the stub outcome.
6. Press **Reject** on a decision. The vehicle stops and **Correct this** opens. Task and the case link are filled from the case and the gateway decision.
7. Type `Our rice is finished. Can someone bring food today?` and press the send arrow. The chooser matches F02 by the food keyword and says it is demo-only.
8. Press the green Call button, speak, then the red end-call button. The in-call screen shows a timer. The phone names Web Speech API, `POST /stt/transcribe`, or the stub transcript. Only a real transcript is sent on.
9. Open "20 scripted calls" and press Step to send the next fixture in index order. The decision log lists the row. Clear log removes it.
10. Press **Reset patterns**. Open **Prompts** and send "We're fine. Really. No need to send anyone." four times, waiting for each feed to finish. The first two stay **REJECTED** and name System 2. The third and fourth say the call has been handled the same way 3 times, so the fast path can take it, and the bars say **ACCEPTED**. Pattern memory shows "Says they are fine" moving from System 2 to System 1. The block map stays above the feed.
