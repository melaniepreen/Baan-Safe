"""Run the four ingest clients and refresh data/SOURCES.md."""

from __future__ import annotations

import sys

from ingest.db import connect, init_db, reset_data
from config.envfile import load_env_file
from ingest import admin_districts, gdacs, gistda, hdx, open_meteo, overpass, reliefweb, thaiwater
from ingest.export import export_data, seed_db
from ingest.report import write_sources
from paths import ROOT


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    refresh = "--refresh" in args
    start = "all"
    if "--from" in args:
        start = args[args.index("--from") + 1]
    load_env_file()
    init_db()
    if start != "all":
        with connect() as conn:
            if conn.execute("SELECT COUNT(*) FROM districts").fetchone()[0] == 0:
                seed_db(conn, ROOT / "data" / "processed")
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
        with connect() as conn:
            export_data(conn, ROOT / "data" / "processed")
        write_sources()
        print("wrote data/SOURCES.md and data/processed/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
