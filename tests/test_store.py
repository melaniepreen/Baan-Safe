"""ingest.store reads the committed JSON/GeoJSON; ingest.export round-trips it."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from ingest import store
from ingest.db import SCHEMA
from ingest.export import export_data, seed_db
from paths import ROOT

DATA = ROOT / "data" / "processed"


def test_committed_counts_and_facility_coords():
    assert len(store.rows("districts")) == 50
    assert len(store.rows("admin_districts")) == 108
    assert len(store.rows("weather_observation")) == 1900
    assert len(store.rows("disaster_report")) == 126
    assert len(store.rows("source_status")) == 47
    layers = {}
    for props, geom in store.flood_shapes():
        layers[props.get("layer")] = layers.get(props.get("layer"), 0) + 1
    assert layers == {"flood_extent": 298, "repeat_flood": 400}
    facilities = store.facilities()
    assert len(facilities) == 4218
    assert all(
        isinstance(f["lat"], float) and isinstance(f["lon"], float) for f in facilities
    )


def test_table_files_are_one_row_per_line_with_thai_text():
    for table in store.TABLES:
        path = DATA / f"{table}.json"
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(store.rows(table)) + 2, table
    admin_text = (DATA / "admin_districts.json").read_text(encoding="utf-8")
    assert "อำเภอ" in admin_text or "เมือง" in admin_text
    assert "\\u0e" not in admin_text.lower()


def test_unknown_table_raises_and_missing_file_is_empty(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        store.rows("infrastructure")
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store._cache.clear()
    assert store.rows("districts") == []


def test_cache_reloads_when_mtime_changes(tmp_path, monkeypatch):
    assert store.rows("districts") is store.rows("districts")
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store._cache.clear()
    path = tmp_path / "districts.json"
    path.write_text(json.dumps([{"name_en": "Old"}]), encoding="utf-8")
    assert store.rows("districts") == [{"name_en": "Old"}]
    path.write_text(json.dumps([{"name_en": "New"}]), encoding="utf-8")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
    assert store.rows("districts") == [{"name_en": "New"}]
    monkeypatch.setattr(store, "DATA_DIR", ROOT / "data" / "processed")
    store._cache.clear()


def test_export_seed_round_trip(tmp_path):
    db1 = tmp_path / "a.sqlite"
    conn = sqlite3.connect(db1)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO districts (location_id, name_en, name_th, lat, lon, province, source)"
        " VALUES ('t1','Mueang X','เมือง',18.0,99.0,'X Province','synthetic')"
    )
    conn.execute(
        "INSERT INTO admin_districts (location_id, name_en, name_th, province, province_code, lat, lon, source)"
        " VALUES ('a1','X District','X','X Province','XX',18.0,99.0,'synthetic')"
    )
    conn.execute(
        "INSERT INTO weather_observation (location_id, timestamp, rainfall_mm, temperature_c, wind_speed_kph, source)"
        " VALUES ('t1','2026-01-01T00:00:00Z',1.5,25.0,3.0,'synthetic')"
    )
    conn.execute(
        "INSERT INTO disaster_report (report_id, event_id, source, published_at, title, summary,"
        " affected_people, affected_households, fatalities, provinces, assistance_type, url)"
        " VALUES ('r1','e1','synthetic','2026-01-01','t','s',0,0,0,'[]','x','u')"
    )
    conn.execute(
        "INSERT INTO source_status (source, fetched_at, row_count, status, detail)"
        " VALUES ('synthetic','2026-01-01T00:00:00Z',1,'ok','')"
    )
    poly = {"type": "Polygon", "coordinates": [[[99, 18], [99.1, 18], [99.1, 18.1], [99, 18.1], [99, 18]]]}
    conn.execute(
        "INSERT INTO flood_extent (event_id, date, geometry, source, duration_window, confidence)"
        " VALUES ('e1','2026-01-01',?,'synthetic','1d',0.5)",
        (json.dumps(poly),),
    )
    conn.execute(
        "INSERT INTO repeat_flood (area_id, geometry, frequency, source) VALUES ('a1',?,3.0,'synthetic')",
        (json.dumps(poly),),
    )
    point = {"type": "Point", "coordinates": [99.0, 18.0]}
    conn.execute(
        "INSERT INTO infrastructure (osm_id, type, geometry, name, accessibility_flag, lat, lon)"
        " VALUES ('n1','hospital',?,'H','yes',18.0,99.0)",
        (json.dumps(point),),
    )
    conn.commit()

    out = tmp_path / "processed"
    export_data(conn, out)
    conn.close()

    db2 = tmp_path / "b.sqlite"
    conn2 = sqlite3.connect(db2)
    conn2.executescript(SCHEMA)
    seed_db(conn2, out)

    conn_a = sqlite3.connect(db1)
    conn_a.row_factory = sqlite3.Row
    conn_b = sqlite3.connect(db2)
    conn_b.row_factory = sqlite3.Row
    tables = list(store.TABLES) + ["flood_extent", "repeat_flood", "infrastructure"]
    for table in tables:
        rows_a = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in conn_a.execute(f"SELECT * FROM {table} ORDER BY rowid")
        ]
        rows_b = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in conn_b.execute(f"SELECT * FROM {table} ORDER BY rowid")
        ]
        assert rows_a == rows_b, table
    conn_a.close()
    conn_b.close()


def test_unavailable_data_returns_enrichment_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store._cache.clear()
    assert not store.available()
    from enrich.context import location_context

    ctx = location_context("Mae Mo")
    assert ctx["matched_district"] is None
    assert ctx["in_flood_extent_1d"] is False
    assert ctx["nearest_hospitals"] == []
