# Data sources

SQLite path: `data/processed/baansafe.sqlite`. Production database is `TODO_HUMAN` in `config/decisions.yaml`. Raw responses are cached under `data/raw/` (gitignored).

Article bodies are not stored. ReliefWeb rows, when a human supplies an approved `appname`, keep a short summary only (headline, truncated to 280 characters).

## Do not collect

- names of people
- national ID numbers
- household addresses or precise home locations
- PromptPay or bank details
- medical records
- immigration status
- criminal history
- individual aid-application statuses

## Fetched this run

| table | rows |
|---|---|
| flood_extent | 63 |
| repeat_flood | 0 |
| disaster_report | 0 |
| weather_observation | 518 |
| infrastructure | 1350 |
| districts | 14 |

| source | status | rows | fetched_at | detail |
|---|---|---|---|---|
| gistda_arcgis | ok | 63 | 2026-10-23T22:27:36.326194+00:00 | ArcGIS MapServer public fallback. Layer 0 (flood-affected extent) count=0. Layer 1 (flood-risk polygons) stored=63 with duration_window=flood_risk_layer. These are not 1/3/7/30-day extents and they are not repeated-flood frequencies. repeat_flood was not filled because the frequency API needs the GISTDA key. |
| gistda_open_api | blocked | 0 | 2026-10-23T22:27:36.411369+00:00 | GISTDA open API requires an API key. Sign-up steps: 1) Open https://api-gateway.gistda.or.th (registration is also described at https://api-gateway.gistda.or.th/v2). 2) Create an API key. 3) Export it as GISTDA_API_KEY in the environment (do not commit it). 4) Re-run `make ingest-refresh`. Documented extent URL pattern: https://api-gateway.gistda.or.th/api/2.0/resources/gi-service/v1.0/disasters/flood-extent-1day?lat={latitude}&lon={longitude}&api_key=REDACTED (same family for 3, 7 and 30 day windows, plus repeated-flood areas). Catalogue: https://opendata.gistda.or.th/dataset/flood-disaster-data and https://disaster.gistda.or.th/services/open-api. Contact published on the catalogue: disaster@gistda.or.th. |
| open_meteo | ok | 518 | 2026-10-23T22:27:52.507607+00:00 | Daily rows=518 for 14 locations. Archive 2026-09-24 to 2026-10-23, forecast 7 days. Granularity is daily (config/ingest.yaml). robots.txt on the API hosts is Disallow: /; calls were made because open_meteo_documented_api_despite_robots_disallow is true. |
| overpass_admin | ok | 14 | 2026-10-23T22:27:38.629797+00:00 | Stored 14 districts whose centres are within 25.0 km of a flood polygon centroid. Assignment is nearest centre, not a boundary intersection. |
| overpass_facilities | ok | 1350 | 2026-10-23T22:28:03.905945+00:00 | Stored 1350 facilities inside the flood-polygon bbox (17.719,99.401,18.840,100.571). accessibility_flag uses flood-extent windows only, not the flood-risk layer. Waterways are centre points, not full lines, to keep the pull bounded. |
| reliefweb | blocked | 0 | 2026-10-23T22:28:03.969028+00:00 | BLOCKED: ReliefWeb requires a pre-approved appname on every request. Sign-up: https://apidoc.reliefweb.int/parameters#appname (short form linked from that page; ReliefWeb replies by email). Then export RELIEFWEB_APPNAME and re-run `make ingest-refresh`. API v1 is decommissioned; use v2. The disaster id named in the brief is fl-2025-000209-tha. No report bodies were stored. Probe stopped: robots.txt disallows /v2/reports on api.reliefweb.int. |

## Later — human to approve

- DDPM reports: later — human to approve. Not fetched.
- aid-payment aggregates: later — human to approve. Not fetched.
- TMD: later — human to approve. Not fetched.
- RID/NWCC: later — human to approve. Not fetched.
- WorldPop: later — human to approve. Not fetched.
- HDX: later — human to approve. Not fetched.
- EM-DAT: later — human to approve. Not fetched.
- World Bank 2011: later — human to approve. Not fetched.
- policy corpus: later — human to approve. Not fetched.
