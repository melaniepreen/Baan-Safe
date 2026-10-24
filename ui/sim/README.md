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

`Correct this` sits in the backend panel after a spoken or typed call, and after a priority sample. The form fills `task` and `input_ref` from the case and the gateway decision. The operator picks `output_correct` from the closed enum for that task and types a reason. The post is `POST /cases/{case_id}/corrections` with `source` `human` and `corrected_by` `operator`. The same form is on the transcript player.

The panel on the right lights the path as the payload comes back: Mubit gateway, System 1 or System 2 (one of them), Banyan Sapling, decision router, next action. The log shows priority, route, needs, next question, and the trace stages from `GET /cases/{id}/trace`. Sapling lights only when this payload contains `sapling_verdict`. An aid route is in scope (`config/decisions.yaml` `sapling_scope` is `aid_eligibility,denial`) but the stub gateway does not call `system2/sapling.py`, so that step stays marked stub and does not invent a verdict.

P1, P2, P3, and P4 light the houses whose **gateway** `final_priority` matches, and move a marker along `response_routes` for those houses. P1 is the boat from the jetty, a supply run from the water desk, and the walk to the shelter. P2 is the evacuation. P3 is the welfare load. P4 is the notice from the school. Where the street is flooded the same run switches to boat. Nothing is drawn as a straight line across a roof. The priority text quotes `config/priorities.yaml` and, separately, a suggestion from `research/thai-flood-management.md` that is not repo policy (`data/responses.json`).

`Play 20 calls` walks `fixtures/index.json` in order through the same case-turn path. The line on the picture runs from the call to the Mubit chip to the house. Lights are the gateway priority: P1 red, P2 amber, P3 yellow, P4 blue. `Step` sends one call. `Reset` clears the lights. F09 is the same house as F08. F07 is the school. F16 is the shelter. Flood level is the depths in `flood.json`. It rises on its own. There is no slider.

`BaanSafeSim.setStatus` still changes `sim_status` in the page only. There is no inspect panel.

## Demo script

Open http://127.0.0.1:8000/ui/sim/ with `make serve` already running. `data.demo_event` stays unset.

1. Watch the flood rise to `flood.json`. The phone's first note says this block is a placeholder, not the unfetched EOS-RS Bangkok map.
2. Press **System 1**. The line is F02 (rice finished, no danger). The chooser note says it is a preset. The flow lights Mubit, then System 1, and leaves System 2 and Sapling off. The house lights P3 and a load moves from the water desk along the drawn roads. The phone quotes the stub reason. **Correct this** appears under the backend log. Task and the case link are filled from the case and the gateway decision.
3. Press **System 2**. The line is F10 (oxygen, water rising). The flow lights System 2. The reason on the step is the stub outcome. A boat runs from the jetty on the canal and the flooded streets.
4. Press **Sapling check**. The line is F17 (renter told they are not eligible). The route is `aid_caseworker`. Sapling's step is the dashed stub: the scope matches, and this result has no `sapling_verdict`. The phone says a human is required. Do not treat `mocks/sapling_stub` as this household's verdict.
5. Press **P1**, then **P3**, then **P4**, then **P2**. Each button triages any fixture the gateway has not seen yet, then moves one route per matching house. Read the policy line and the suggestion line in the backend log. They are different texts.
6. Type `Our rice is finished. Can someone bring food today?` and press Send. The chooser matches F02 by the food keyword and says it is demo-only.
7. Press Call, speak, then Stop. The phone names Web Speech API, `POST /stt/transcribe`, or the stub transcript. Only a real transcript is sent on.
8. Open "20 scripted calls" and press Step to send the next fixture in index order.
