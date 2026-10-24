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

Open http://127.0.0.1:8000/ui/sim/ . The block renders from the JSON files. The API chip says local data only.

Regenerate the JSON after editing the layout script:

```bash
python3 ui/sim/build_town.py
```

## What is real, and what is a placeholder

`data.demo_event` is still unset. The fixtures name districts (Lampang, Phrae, Nan, Phayao), not streets. This block puts a few of those households on one picture so an operator can point at them. It is not a map of one town, and it is not a cadastral plan.

| Piece | Where it lives | Contract |
|---|---|---|
| Household on a house | `data/town.json` `buildings[].household` | `Household`. `location_label` is the fixture district. No house number. |
| Status (`clear`, `at_risk`, `flooded`, `needs_help`, `evacuated`) | `buildings[].sim_status` | Not a contract field. `BaanSafeSim.setStatus(householdId, status)` changes it in the page only. |
| Hazard | `data/flood.json` and `town.json` `hazards` | `Hazard` with `kind: flood`. Local metres, not WGS84. |
| Dispatch category on a drawn path | `town.json` `routes[].contract_route` | `Route` enum (`shelter_placement`, `rescue_coordination`). The enum is not a polyline. |
| Path geometry | `town.json` `graph` plus `routes[].node_ids` | No path API. The line is the shortest walk on the placeholder graph. `F06` is on foot. `F10` is by boat. |
| Boats, shelter, clinic van, water desk | placed on buildings, ids from `mocks/resources.json` | `Resource`, and `GET /resources` when the API is up. |
| Live flood flags | not drawn as this grid | `GET /context?district=…` and `GET /map/flood`. The WGS84 polygons are a different picture. |

Street names are in `data/streets.json`. Every name is marked placeholder (`จำลอง` / `PLACEHOLDER`). Replace that file to use real names. Household records do not store the street.

Click a block to read it. The status buttons mark that household in the page. `Run gateway triage` loads the fixture and `POST`s its `case_state` to `/triage`. The router answer is whatever the stub gateway returns. It does not write the household status.

`F06` walks to the fictional north hall (`shelter_placement`). `F10` is the boat run from the jetty (`rescue_coordination`). Both are on when the page opens.
