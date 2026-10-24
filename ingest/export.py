"""Export the ingest SQLite cache to committed JSON/GeoJSON, and seed the cache from it."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ingest import store
from ingest.db import SCHEMA
from ingest.geo import loads
from paths import ROOT

_TABLE_COLUMNS = {
    "districts": ["location_id", "name_en", "name_th", "lat", "lon", "province", "source"],
    "admin_districts": ["location_id", "name_en", "name_th", "province", "province_code", "lat", "lon", "source"],
    "weather_observation": ["location_id", "timestamp", "rainfall_mm", "temperature_c", "wind_speed_kph", "source"],
    "disaster_report": [
        "report_id", "event_id", "source", "published_at", "title", "summary",
        "affected_people", "affected_households", "fatalities", "provinces",
        "assistance_type", "url",
    ],
    "source_status": ["source", "fetched_at", "row_count", "status", "detail"],
}


def _table_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    cols = ", ".join(_TABLE_COLUMNS[table])
    return [dict(row) for row in conn.execute(f"SELECT {cols} FROM {table} ORDER BY rowid")]


def _flood_features(conn: sqlite3.Connection) -> list[dict]:
    features = []
    for row in conn.execute(
        "SELECT event_id, date, geometry, source, duration_window, confidence FROM flood_extent ORDER BY rowid"
    ):
        features.append(
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
    for row in conn.execute(
        "SELECT area_id, geometry, frequency, source FROM repeat_flood ORDER BY rowid"
    ):
        features.append(
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
    return features


def _facility_features(conn: sqlite3.Connection) -> list[dict]:
    features = []
    for row in conn.execute(
        "SELECT osm_id, type, geometry, name, accessibility_flag FROM infrastructure ORDER BY rowid"
    ):
        features.append(
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
    return features


def export_data(conn: sqlite3.Connection, data_dir: Path) -> None:
    for table in store.TABLES:
        store.write_rows(table, _table_rows(conn, table), data_dir)
    flood_features = _flood_features(conn)
    store.write_features(data_dir / "flood.geojson", flood_features)
    store.write_features(data_dir / "facilities.geojson", _facility_features(conn))
    # Touch geometries once so a bad polygon fails here, not in the API.
    for feature in flood_features:
        loads(json.dumps(feature["geometry"]))


def seed_db(conn: sqlite3.Connection, data_dir: Path) -> None:
    conn.executescript(SCHEMA)
    for table in store.TABLES:
        path = data_dir / f"{table}.json"
        if not path.exists():
            continue
        cols = _TABLE_COLUMNS[table]
        placeholders = ",".join("?" for _ in cols)
        for row in json.loads(path.read_text(encoding="utf-8")):
            conn.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                tuple(row.get(col) for col in cols),
            )
    path = data_dir / "flood.geojson"
    if path.exists():
        for feature in json.loads(path.read_text(encoding="utf-8")).get("features") or []:
            props = feature.get("properties") or {}
            geom = json.dumps(feature["geometry"])
            if props.get("layer") == "flood_extent":
                conn.execute(
                    "INSERT INTO flood_extent (event_id, date, geometry, source, duration_window, confidence)"
                    " VALUES (?,?,?,?,?,?)",
                    (props.get("event_id"), props.get("date"), geom, props.get("source"),
                     props.get("duration_window"), props.get("confidence")),
                )
            elif props.get("layer") == "repeat_flood":
                conn.execute(
                    "INSERT INTO repeat_flood (area_id, geometry, frequency, source) VALUES (?,?,?,?)",
                    (props.get("area_id"), geom, props.get("frequency"), props.get("source")),
                )
    path = data_dir / "facilities.geojson"
    if path.exists():
        for feature in json.loads(path.read_text(encoding="utf-8")).get("features") or []:
            props = feature.get("properties") or {}
            coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
            conn.execute(
                "INSERT INTO infrastructure (osm_id, type, geometry, name, accessibility_flag, lat, lon)"
                " VALUES (?,?,?,?,?,?,?)",
                (props.get("osm_id"), props.get("type"), json.dumps(feature["geometry"]),
                 props.get("name"), props.get("accessibility_flag"), coords[1], coords[0]),
            )
    conn.commit()


def main() -> int:
    from ingest.db import connect

    with connect() as conn:
        export_data(conn, ROOT / "data" / "processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
