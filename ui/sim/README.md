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

## Hosting on Modal

The public demo is the Modal app `baansafe-gateway` (`infra/modal/gateway_app.py`). One `*.modal.run` URL serves `/ui/sim/`, `POST /triage`, `/cases`, and `POST /stt/transcribe`. The default deploy uses the stub gateway. It does not need a secret, a GPU, or a Hugging Face token.

From the repo root:

```bash
pip install modal
modal setup
modal deploy infra/modal/gateway_app.py
```

`make deploy-modal` runs that deploy command. Modal prints the URL when the deploy finishes. The same app is listed at https://modal.com/apps/baansafe/main. Open `/ui/sim/` on the printed host.

Traces, corrections, training events, policy pins, and the hazard database are written to the `baansafe-demo` volume mounted at `/data`. Cases stay in memory until the container scales down.

Optional upstreams, all unset by default. Export one before `modal deploy` to bake it into that deploy:

- `STT_UPSTREAM` — base URL of a deployed `baansafe-stt` app. `POST /stt/transcribe` forwards the upload to `{STT_UPSTREAM}/transcribe`. When it is unset, the route returns an empty `text` and the phone keeps the stub transcript. No words are invented.
- `S1_UPSTREAM`, `S2_UPSTREAM`, `SAPLING_UPSTREAM` — recorded on `GET /hosting` when they are http(s) URLs. Triage stays on stub outcomes. Those apps do not return a gateway outcome, and `S1_IMPL`, `S2_IMPL`, and `SAPLING_IMPL` stay `stub`.

## What is drawn, and what stays a fixture

`data.demo_event` is still unset. The picture is a local-metre block of real Sukhumvit streets in Watthana, not a cadastral survey. The HDX set `eos-rs-thailand-flood-bangkok-sep-2026` is listed in `data/SOURCES.md` and was not fetched. Household `location_label` stays the fixture district (Lampang, Phrae, Nan, Phayao). `flood.json` is local metres, not that Bangkok map. Flooded ground is a murky brown-teal, darker where the depth is greater, with a soft edge. Wat That Thong's compound is the dry hole.

| Piece | Where it lives | Contract |
|---|---|---|
| Household on a house | `data/town.json` `buildings[].household` | `Household`. `location_label` is the fixture district. No house number. |
| Status (`clear`, `at_risk`, `flooded`, `needs_help`, `evacuated`) | `buildings[].sim_status` | Not a contract field. `BaanSafeSim.setStatus(householdId, status)` changes it in the page only. |
| Hazard | `data/flood.json` and `town.json` `hazards` | `Hazard` with `kind: flood`. Local metres, not WGS84. |
| Dispatch category on a drawn path | `town.json` `routes[].contract_route` | `Route` enum (`shelter_placement`, `rescue_coordination`). The enum is not a polyline. |
| Path geometry | `town.json` `graph`, `routes[]`, and `response_routes[]` | No path API. `routes` keeps the F06 foot path and the F10 boat path. `response_routes` is one path per call from the jetty, shelter, Sun Chuai Lue Nam Thuam, and school. A run may change from foot to boat where the drawn street changes mode. Lanes are extra edges flagged `lane`. |
| Boats, shelter, clinic van, Sun Chuai Lue Nam Thuam | placed on buildings, ids from `mocks/resources.json` | `Resource`. `GET /resources` adds public shelters and hospitals from the place snapshot. The drawn mock ids stay on the block. |
| Live flood flags | not drawn as this grid | `GET /context?district=…` and `GET /map/flood`. The WGS84 polygons are a different picture. |

Street names are in `data/streets.json`. `name_th` and `name_en` are the same romanised string, so the map does not draw Thai script. North of Thanon Sukhumvit, west to east: Soi Sukhumvit 39 (Phrom Phong), Soi Sukhumvit 49, Soi Sukhumvit 55 (Thong Lo), Soi Sukhumvit 63 (Ekkamai). South of it: Soi Sukhumvit 24, Soi Sukhumvit 36, Soi Sukhumvit 38, Soi Sukhumvit 40, Soi Sukhumvit 42. Thanon Phetchaburi Tat Mai is the east-west road on the north side. Thanon At Narong (At Narong Road) is the east-west road on the south side. Khlong Saen Saep is drawn on the west edge; the canal itself runs east-west north of Sukhumvit. Odd soi numbers sit on the north side of the drawn Thanon Sukhumvit. Wat That Thong is the temple. It stands on Thanon Sukhumvit beside BTS Ekkamai, between Soi Sukhumvit 63 and Soi Sukhumvit 65; this block draws the compound on the south side of the road. The school is XCL American School, the Sukhumvit campus of XCL American School of Bangkok at 59-59/1 Sukhumvit Soi 49/3. Bangkok Prep's own site now lists 77 Soi Sukhumvit 77, so that name is not used here. The water desk is Sun Chuai Lue Nam Thuam, a flood relief centre. The pink apartment block is Baan Chompoo Apartment. The clinic, evacuation shelter, jetty, white apartment block, and sala keep plain romanised labels. Samitivej Sukhumvit Hospital is on Soi Sukhumvit 49, which is not the clinic plot. Household records do not store the street.

`data/places.json` is the public OpenStreetMap catalog for Lampang, Phrae, Nan, and Phayao. `GET /resources` uses that snapshot. Those northern names are not pinned onto this Sukhumvit picture.

The phone on the left is the caller. Type a line and press Send, or press Call and speak. Call uses the microphone (`MediaRecorder`) and, when the browser has it, the Web Speech API. If `POST /stt/transcribe` answers, that text is used instead. This API does not mount `infra/modal/stt_app`. `speech_to_text.provider` is still `TODO_HUMAN`. When neither path returns words, the phone shows a stub transcript and does not invent a sentence.

`gateway.route_chooser` is still `TODO_HUMAN`, so a case that is not a fixture is not routed. The page has a **DEMO-ONLY chooser** (it is not backend policy). It maps the typed or spoken line to a fixture with a keyword rule or the nearest scripted opening, and the screen says which rule fired. The page then `POST`s `/cases` with that `fixture_id` and `POST`s `/cases/{id}/turns` with the caller's text. The stub gateway answers the fixture id. It does not read the new sentence with a live model. The phone answers from `data/replies.json`: a short scripted operator line in English, with Thai under it when the template has a line. A System 1 fast path that the confidence threshold accepts sends that line at once. A System 2 decision, a cascade, a Sapling aid decision, and a System 1 score under the threshold do not. Those wait on the operator, and the phone says an operator is reviewing the request. After Accept, a question from the stub outcome is asked in the same sentence as the ETA, and a human-required case adds that a colleague will confirm it. A separate note says the reply is scripted, not a live operator. Priority, route, and next action stay in the backend feed.

`Correct this` opens when the operator presses Reject. The form fills `task` and `input_ref` from the case and the gateway decision. The operator picks `output_correct` from the closed enum for that task and types a reason. The post is `POST /cases/{case_id}/corrections` with `source` `human` and `corrected_by` `operator`. The same form is on the transcript player.

The priority comes from the call on the phone. There is no separate P1–P4 button. The stub gateway's `final_priority` lights that house and the draft rulebook picks the vehicle.

The right-hand column holds a small block map above the backend feed. The map does not sit on the town. The phone, the block map, and the feed use a dark navy surface. Accents are the Baan-Safe logo colours: orange `#ED7401`, blue `#0076D8`, teal `#014855`, and navy `#012246`. Red is only the critical and reject colour. The feed plays cards from `data/sim_events.json`. Every card is badged **simulated**, with an icon and one of those shades for Mubit, a tool, System 1, the handoff, System 2 (Nemotron), Sapling, the decision router, or dispatch. The headline is plain English. Technical fields sit in a collapsed detail. A progress line and a gateway priority badge sit at the top. The event shape is `schema_version` `baansafe.sim_activity.v1`: `id`, `kind` (`memory`, `tool`, `system_1`, `handoff`, `system_2`, `sapling`, `router`, `operator_approval`, `dispatch`), `text` with fields to fill, `delay_ms`, `source`, and optional `when` (`rejected`, `aid`, or `approved`) and `fill` (`flood` or `shelter`). For a System 2 call the `operator_approval` step comes before `dispatch`. System 1 scores and need scores live on the scenario. The confidence threshold (default 0.75, the number in the panel) accepts the fast path when the adjusted top score is at least the threshold, and otherwise plays the handoff into the scripted System 2 lines.

Each scenario has a `theme`. Repeating a theme is simulated pattern memory (`localStorage` key `baansafe.sim.pattern-memory`, also listed in the panel). The first time a low-confidence theme appears, System 1 rejects it and System 2 takes it. Each consistent repeat raises that theme's score. After `learning.promote_after` times (3), the feed says the fast path can take it. Life-safety themes (`life_safety: true`, including trapped-oxygen and an unaccompanied child) stay with System 2 until the operator presses Accept; the next repeat of that theme can then take the fast path. Aid themes (`learns: false`) are remembered and stay with System 2 and Sapling. A changed gateway priority starts the count again. Reset patterns clears that memory. Reset on the phone does not.

A real stream can replace the file later. Call `BaanSafeSim.attachLiveFeed(source)` with an `EventSource` or any object that emits `step` events of the same shape. A future gateway path such as `GET /cases/{case_id}/events` (SSE) or a websocket is the place to connect. Set `source` to `gateway` on those objects. Nothing in this API emits that stream today.

Sapling's simulated line uses `supported`, `violation`, `missing`, or `unsure` only as a labelled drill. The stub gateway does not return `sapling_verdict`, and `mocks/sapling_stub` is not this household's verdict.

`data/rulebook.json` is a **DRAFT** table, pending confirmation, and it is not repo policy. The first matching row chooses the picture. Every dispatched truck or van is drawn as the same wooden boat, with a wake even on a road segment: a red-cross flag for a medical run, crates for a supply boat, an orange flag for an evacuation boat. The rulebook `vehicle` keys stay `truck`, `van`, `boat`, `pulse`, and `none`, so the route shape does not change. An evacuation boat still runs shelter to house to shelter. A supply boat is still one way. A rescue boat still leaves the jetty and can continue to the clinic or the shelter. The return to the clinic is a walk on the existing street graph (`route_walk.js`), not a new chord. The SMS pulse is unchanged. A System 1 result at or above the threshold still sends the boat, the pulse, and the phone line on its own. Accept on that path confirms the decision in the log. A System 2 result, including a cascade and a Sapling aid decision that came through System 2, stays PENDING APPROVAL until the operator presses Accept. The feed card, the dispatch frame, and the phone say Awaiting operator approval and name the vehicle, destination, ETA, and matched rule. Nothing moves before that: no boat, no pulse, no destination mark, and no dispatched row in the decision log. Accept then draws the boat or the pulse, writes the log, sends the scripted ETA, and confirms a life-safety pattern. Reject writes a rejection, opens `Correct this`, tells the caller an operator is reassigning, and never draws a vehicle. Reset clears a pending approval as well as any boat already on the map.

The decision log stays on screen under `localStorage` key `baansafe.sim.decision-log` (case, priority, rule, action, operator, time). Clear log empties it. There is no export button. Saved prompts are in `data/prompts.json`. The phone lines for a rescue boat, an evacuation boat, and a supply boat use `eta_min` from the matching draft rule.

The priority text still quotes `config/priorities.yaml` and, separately, a suggestion from `research/thai-flood-management.md` that is not repo policy (`data/responses.json`).

`Play 20 calls` walks `fixtures/index.json` in order through the same case-turn path. There is no Mubit chip and no dotted line on the map. Mubit stays as the label on its feed card. A highlighted building is outlined on its own walls and roof: the caller or incident building is red, a clinic or shelter destination is blue, and other lit houses use red, orange, green, and violet for P1 to P4. `Reset`, beside Dispatch frame and in the feed header, stops the boats, clears a pending approval, clears the dispatch and the outlines, and leaves pattern memory alone. `Step` sends one call. F09 is the same house as F08. F07 is the school. F16 is the shelter. Flood level is the depths in `flood.json`. It rises on its own. There is no slider.

`BaanSafeSim.setStatus` still changes `sim_status` in the page only. There is no inspect panel.

## Demo script

Open http://127.0.0.1:8000/ui/sim/ with `make serve` already running. `data.demo_event` stays unset.

1. Watch the flood rise to `flood.json`. Flooded ground is a murky brown-teal, darker in deeper water. The phone shows Baan-Safe and `+66 81 555 0149`. After `POST /session` records a caller IP, the status reads Connected with a green dot, and the first operator bubble is "You are connected to Baan-Safe. How can we help?" with the Thai line under it. The next note names the Sukhumvit block and says the EOS-RS Bangkok map was not fetched. On this machine the address is the fixed Thai stub `171.6.84.23`, marked DEMO on the feed card. A public `X-Forwarded-For` hop is stored as given.
2. Open **Prompts** and tap the System 1 rice line (F02). The chooser note says it is a saved prompt. The cards badge each step simulated. The first card is the caller IP. The next names the house and its soi. System 1 shows P3 above the threshold and **ACCEPTED**. The house is outlined in green for P3. Sun Chuai Lue Nam Thuam is not a second stop, so only the house is outlined. A supply boat leaves Sun Chuai Lue Nam Thuam along the drawn roads, with a wake and crates. The dashed path and the boat share one pace: at most 54 projected pixels a second, and at least three seconds even on a short hop. Reset clears the trip mid-route. The phone says a supply boat is bringing food and that the reply is scripted. The rulebook row `p3-welfare` highlights, and the decision log gains a row. Press **Accept**.
3. Open **Prompts** and tap the System 2 oxygen line (F10). System 1's top score is under the threshold, so the card says **REJECTED** and the handoff plays, then **PENDING APPROVAL**. The dispatch frame and the phone say Awaiting operator approval. The proposal names the rescue boat, the clinic, about 12 minutes, and rule `p1-medical`. The caller's building is outlined in orange. No boat moves, the clinic is not marked, and the decision log has no dispatched row. The phone says an operator is reviewing the request. Press **Accept**. The boat then leaves the jetty toward the house and on to the clinic, the log gains a dispatched row, and the phone gives the 12 minute line. The pattern row can be confirmed.
4. Open **Prompts** and tap the Sapling rent line (F17). The route is `aid_caseworker`. The location card names `bldg-f17` on Soi Sukhumvit 40. The Sapling card is the simulated verdict (`missing`). The stub gateway has no `sapling_verdict`. This aid decision is also awaiting approval. The phone says an operator is reviewing the request. Press **Accept**. The phone then talks about flood relief aid and a colleague, and says this call cannot promise it. No vehicle is dispatched. The sister line (F18) is a different house, `bldg-f18` on Soi Sukhumvit 42. Do not treat `mocks/sapling_stub` as this household's verdict. Repeating it does not hand the fast path the aid case.
5. Open **Prompts** and the Landmarks group. "Next to a temple" outlines `bldg-0328` beside Wat That Thong. "Baan Chompoo Apartment" outlines `bldg-tower-pink`. "Khlong Saen Saep" outlines `bldg-0441`. The feed names the building, the soi, and a confidence between 0.55 and 0.70, and says the match is not a device GPS fix. Each of those prompts waits for **Accept** before a boat moves. Rice, oxygen, the renter house, and the aid-list house stay on their own buildings.
6. Raise the confidence threshold above 0.82 and send the rice line again. System 1 is **REJECTED**, the handoff plays, and the supply boat waits for **Accept**. The gateway priority badge is still the stub outcome.
7. Send the oxygen line again and press **Reject** while it is awaiting approval. No boat appears. The decision log records the rejection. The phone says an operator is reassigning. **Correct this** opens. Task and the case link are filled from the case and the gateway decision. On a System 1 call that already dispatched, Reject still stops the boat and opens the same form.
8. Type `Our rice is finished. Can someone bring food today?` and press the send arrow. The chooser matches F02 by the food keyword and says it is demo-only.
9. Press the blue Call button, speak, then the red end-call button. The in-call screen shows a timer. The phone names Web Speech API, `POST /stt/transcribe`, or the stub transcript. Only a real transcript is sent on.
10. Open "20 scripted calls" and press Step to send the next fixture in index order. The decision log lists the row. Clear log removes it.
11. Press **Reset patterns**. Open **Prompts** and send "We're fine. Really. No need to send anyone." four times, waiting for each feed to finish. The first two stay **REJECTED** and name System 2. The third and fourth say the call has been handled the same way 3 times, so the fast path can take it, and the bars say **ACCEPTED**. Pattern memory shows "Says they are fine" moving from System 2 to System 1. The block map stays above the feed.

## Learning loop

This page does not draw a learning-loop button or panel. `make rl-loop`, `make rl-loop-replay`, and `GET /rl/run` stay on the API.

When `decision.source_outcomes.length > 1` (a cascade turn), the backend flow shows System 1 → **handoff** → System 2: `[0]` is the deciding System 2 outcome and `[1]` is the System 1 outcome that escalated.
