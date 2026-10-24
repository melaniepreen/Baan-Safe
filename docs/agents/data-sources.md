---
title: Live public data sources
tags: [ingest, snapshots, gistda, open-meteo, overpass, gazetteer]
files:
  - ingest/demo_sources.py
  - ingest/snapshots.py
  - config/escalation.yaml
  - system1/extract.py
  - enrich/context.py
---

## Purpose

Checked public feeds for the fixture provinces (Lampang, Phrae, Nan, Phayao) and kept a small committed copy under `data/snapshots/`. Raw bodies stay in `data/raw/` and are gitignored. ReliefWeb and DDPM are not sources.

## Key files

- `ingest/demo_sources.py` — live refresh and offline status.
- `ingest/snapshots.py` — read and write the committed JSON. A credential marker is refused.
- `data/snapshots/` — gazetteer, places, rain, GISTDA probe, RID dams, TMD failure, geoBoundaries metadata.
- `ui/sim/data/places.json` — the same public places for the town page.
- `enrich/context.py` — rain and the near-flood buffer as data on the case.
- `mocks/loader.py` — `load_dispatch_resources()` for shelters and hospitals.

## Interfaces/contracts

`make sources-refresh` calls the network and rewrites the snapshots. `make sources-status` only reads them.

| id | status | URL | licence | rate limit |
|---|---|---|---|---|
| gistda_open_api | blocked | `https://api-gateway.gistda.or.th/api/2.0/resources/features/flood/1day` | GISTDA open API, key required | One probe. No key was sent. HTTP 407. |
| gistda_arcgis | ok | `https://gistdaportal.gistda.or.th/arcgis/rest/services/app/GISTDA_flood/MapServer` | Public MapServer | Two count queries. Layer 0 count 0. Layer 1 count 63. |
| open_meteo | ok | `https://api.open-meteo.com/v1/forecast` and `archive-api.open-meteo.com` | CC BY 4.0 | Free API is about 10,000 calls a day. Eight calls per refresh. robots.txt is Disallow: /; the documented API is allowed in `config/ingest.yaml`. |
| overpass_places | ok | `https://overpass.openstreetmap.fr/api/interpreter` | ODbL | No robots.txt on this host. One query per town or fixture district, at most one per second. `overpass-api.de` is not used. |
| hdx_cod_ab | ok | `https://data.humdata.org/dataset/cod-ab-tha` | CC BY-IGO | One spreadsheet. 928 ADM2 rows. Tambon geometry is not stored. The object-storage redirect is not written down. |
| geoboundaries | available_not_used | `https://www.geoboundaries.org/api/current/gbOpen/THA/ADM2/` | CC BY 3.0 IGO | Crawl-delay 10. Metadata only. COD-AB has the Thai names. |
| rid_dams | ok | `https://app.rid.go.th/reservoir/api/dam/public` | Public RID JSON, no licence page on the payload | One request. robots.txt is HTTP 404. Northern dams have no coordinates, so they are not a district flag. |
| tmd | failed | `https://data.tmd.go.th/` | Nothing stored | robots.txt disallows `/`. That host was not called. `www.tmd.go.th/api/weather` returned HTML, not observations. |

Keyword extraction matches Thai and English district names from the gazetteer. `near_flood_extent`, `heavy_rain_forecast`, and `heavy_rain_observed` are data flags from `enrichment_flags`. They do not change priority. Shelters are schools and temples. Hospitals are ambulance units. Ferry terminals are boats. Fire stations stay on the place list.

## Invariants

- Do not fetch ReliefWeb. Do not add DDPM.
- Do not print or store `GISTDA_API_KEY`. The HDX file redirect is not committed.
- Callers stay synthetic. Snapshots store district names and public facilities, not phones or home addresses.
- Enrichment does not change `final_priority`.
- A failed refresh keeps the previous snapshot so the demo still runs.

## How to test

- `tests/test_live_sources.py` reads the snapshots and does not open a socket.
- `make sources-status` prints the table above from disk.
- `make test` and `make validate`.

## Common pitfalls

- Putting the GISTDA key in a status string or a cache URL.
- Saving the HDX object-storage redirect. It carries a short-lived signature.
- Treating an RID dam total as the water at a caller's district. The feed has no coordinates.
- Calling `data.tmd.go.th` after robots.txt disallows it.
- Letting a data flag route the case or change priority.

## Open TODO_HUMAN keys

This catalogue does not invent leaf values. `data.demo_event` is decided (`Hat Yai / Songkhla`). `data.production_db` stays `TODO_HUMAN`. `GISTDA_API_KEY` is an environment variable, not a decision leaf.
