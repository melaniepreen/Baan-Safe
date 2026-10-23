"""Write data/SOURCES.md from SQLite row counts and source status."""

from __future__ import annotations

from ingest.db import DB_PATH, connect

LATER = [
    "DDPM reports",
    "aid-payment aggregates",
    "TMD",
    "RID/NWCC",
    "WorldPop",
    "HDX",
    "EM-DAT",
    "World Bank 2011",
    "policy corpus",
]

DO_NOT_COLLECT = [
    "names of people",
    "national ID numbers",
    "household addresses or precise home locations",
    "PromptPay or bank details",
    "medical records",
    "immigration status",
    "criminal history",
    "individual aid-application statuses",
]


def write_sources() -> str:
    path = DB_PATH.parent.parent / "SOURCES.md"
    lines = [
        "# Data sources",
        "",
        "SQLite path: `data/processed/baansafe.sqlite`. Production database is `TODO_HUMAN` in `config/decisions.yaml`. Raw responses are cached under `data/raw/` (gitignored).",
        "",
        "Article bodies are not stored. ReliefWeb rows, when a human supplies an approved `appname`, keep a short summary only (headline, truncated to 280 characters).",
        "",
        "## Do not collect",
        "",
    ]
    for item in DO_NOT_COLLECT:
        lines.append(f"- {item}")
    lines.extend(["", "## Fetched this run", ""])
    if not DB_PATH.exists():
        lines.append("No database yet. Run `make ingest`.")
        lines.append("")
    else:
        with connect() as conn:
            status_rows = conn.execute(
                "SELECT source, fetched_at, row_count, status, detail FROM source_status ORDER BY source"
            ).fetchall()
            counts = {
                "flood_extent": _count(conn, "flood_extent"),
                "repeat_flood": _count(conn, "repeat_flood"),
                "disaster_report": _count(conn, "disaster_report"),
                "weather_observation": _count(conn, "weather_observation"),
                "infrastructure": _count(conn, "infrastructure"),
                "districts": _count(conn, "districts"),
            }
        lines.append("| table | rows |")
        lines.append("|---|---|")
        for name, count in counts.items():
            lines.append(f"| {name} | {count} |")
        lines.extend(["", "| source | status | rows | fetched_at | detail |", "|---|---|---|---|---|"])
        for row in status_rows:
            detail = " ".join(str(row["detail"] or "").split())
            lines.append(
                f"| {row['source']} | {row['status']} | {row['row_count']} | {row['fetched_at']} | {detail} |"
            )
        lines.append("")
    lines.extend(["## Later — human to approve", ""])
    for name in LATER:
        lines.append(f"- {name}: later — human to approve. Not fetched.")
    lines.append("")
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


def _count(conn, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])


if __name__ == "__main__":
    print(write_sources())
