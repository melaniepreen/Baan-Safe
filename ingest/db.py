"""SQLite storage for normalised public hazard data. Not the production database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from paths import ROOT


def _default_db_path() -> Path:
    """BAANSAFE_DB_PATH overrides the repo file. Read when this module is imported."""
    raw = os.environ.get("BAANSAFE_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    return ROOT / "data" / "processed" / "baansafe.sqlite"


DB_PATH = _default_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS flood_extent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    date TEXT,
    geometry TEXT NOT NULL,
    source TEXT,
    duration_window TEXT,
    confidence REAL
);
CREATE TABLE IF NOT EXISTS repeat_flood (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id TEXT,
    geometry TEXT NOT NULL,
    frequency REAL,
    source TEXT
);
CREATE TABLE IF NOT EXISTS disaster_report (
    report_id TEXT PRIMARY KEY,
    event_id TEXT,
    source TEXT,
    published_at TEXT,
    title TEXT,
    summary TEXT,
    affected_people INTEGER,
    affected_households INTEGER,
    fatalities INTEGER,
    provinces TEXT,
    assistance_type TEXT,
    url TEXT
);
CREATE TABLE IF NOT EXISTS weather_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT,
    timestamp TEXT,
    rainfall_mm REAL,
    temperature_c REAL,
    wind_speed_kph REAL,
    source TEXT
);
CREATE TABLE IF NOT EXISTS infrastructure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    osm_id TEXT,
    type TEXT,
    geometry TEXT,
    name TEXT,
    accessibility_flag TEXT,
    lat REAL,
    lon REAL
);
CREATE TABLE IF NOT EXISTS districts (
    location_id TEXT PRIMARY KEY,
    name_en TEXT,
    name_th TEXT,
    lat REAL,
    lon REAL,
    province TEXT,
    source TEXT
);
CREATE TABLE IF NOT EXISTS admin_districts (
    location_id TEXT PRIMARY KEY,
    name_en TEXT,
    name_th TEXT,
    province TEXT,
    province_code TEXT,
    lat REAL,
    lon REAL,
    source TEXT
);
CREATE TABLE IF NOT EXISTS source_status (
    source TEXT PRIMARY KEY,
    fetched_at TEXT,
    row_count INTEGER,
    status TEXT,
    detail TEXT
);
"""

DATA_TABLES = [
    "flood_extent",
    "repeat_flood",
    "disaster_report",
    "weather_observation",
    "infrastructure",
    "districts",
    "admin_districts",
    "source_status",
]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def reset_data() -> None:
    init_db()
    with connect() as conn:
        for table in DATA_TABLES:
            conn.execute(f"DELETE FROM {table}")


def set_status(
    source: str,
    *,
    fetched_at: str,
    row_count: int,
    status: str,
    detail: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO source_status (source, fetched_at, row_count, status, detail)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                fetched_at=excluded.fetched_at,
                row_count=excluded.row_count,
                status=excluded.status,
                detail=excluded.detail
            """,
            (source, fetched_at, row_count, status, detail),
        )


def db_exists() -> bool:
    return DB_PATH.exists()
