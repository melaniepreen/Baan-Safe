"""Run the four ingest clients and refresh data/SOURCES.md."""

from __future__ import annotations

import json
import sys

from ingest.db import connect, init_db, reset_data
from ingest.geo import loads
from config.envfile import load_env_file
from ingest import admin_districts, gdacs, gistda, hdx, open_meteo, overpass, reliefweb, thaiwater
from ingest.report import write_sources
from paths import ROOT


def export_geojson() -> None:
    folder = ROOT / "data" / "processed"
    folder.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        flood_rows = conn.execute(
            "SELECT event_id, date, geometry, source, duration_window, confidence FROM flood_extent"
        ).fetchall()
        repeat_rows = conn.execute(
            "SELECT area_id, geometry, frequency, source FROM repeat_flood"
        ).fetchall()
        facility_rows = conn.execute(
            "SELECT osm_id, type, geometry, name, accessibility_flag FROM infrastructure"
        ).fetchall()
    flood_features = []
    for row in flood_rows:
        flood_features.append(
            {
                "type": "Feature",
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "event_id": row["event_id"],
                    "date": row["date"],
                    "source": row["source"],
                    "duration_window": row["duration_window"],
                    "confidence": row["confidence"],
                    "layer": "flood_extent",
                },
            }
        )
    for row in repeat_rows:
        flood_features.append(
            {
                "type": "Feature",
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "area_id": row["area_id"],
                    "frequency": row["frequency"],
                    "source": row["source"],
                    "layer": "repeat_flood",
                },
            }
        )
    facilities = []
    for row in facility_rows:
        facilities.append(
            {
                "type": "Feature",
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "osm_id": row["osm_id"],
                    "type": row["type"],
                    "name": row["name"],
                    "accessibility_flag": row["accessibility_flag"],
                },
            }
        )
    (folder / "flood.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": flood_features}) + "\n",
        encoding="utf-8",
    )
    (folder / "facilities.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": facilities}) + "\n",
        encoding="utf-8",
    )
    # Touch geometries once so a bad polygon fails here, not in the API.
    for feature in flood_features:
        loads(json.dumps(feature["geometry"]))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    refresh = "--refresh" in args
    start = "all"
    if "--from" in args:
        start = args[args.index("--from") + 1]
    load_env_file()
    init_db()
    if start == "all":
        reset_data()
        print("gistda:", gistda.ingest(refresh)[:1200])
        print("hdx:", hdx.ingest(refresh)[:1200])
    if start in {"all", "gdacs"}:
        print("gdacs:", gdacs.ingest(refresh)[:1200])
        print("overpass admin:", overpass.ingest_admin(refresh)[:1200])
        print("open-meteo:", open_meteo.ingest(refresh)[:800])
        print("overpass facilities:", overpass.ingest_facilities(refresh)[:1200])
        print("thaiwater:", thaiwater.ingest(refresh)[:800])
        print("reliefweb:", reliefweb.ingest(refresh)[:400])
        print("overpass gazetteer:", admin_districts.ingest(refresh)[:1200])
        export_geojson()
        write_sources()
        print("wrote data/SOURCES.md and data/processed/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
