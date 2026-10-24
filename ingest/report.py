"""Write data/SOURCES.md from the committed data files and source status."""

from __future__ import annotations

from ingest import store
from paths import ROOT

LATER = [
    "aid-payment aggregates",
    "TMD registered warning API",
    "RID reservoir API",
    "WorldPop",
    "HDX admin boundaries",
    "EM-DAT",
    "World Bank 2011 loss tables",
    "policy corpus",
]

LATER_NOTES = {
    "policy corpus": (
        "drafted in `policies/` on 24 October 2026 and served by the policy service "
        "(`local_yaml` is the only live adapter). See `policies/SOURCES.md`. Which rule ids "
        "are authoritative for the demo is `policies.authoritative_set` and is still "
        "`TODO_HUMAN`. ReliefWeb and DDPM were not used. Remote catalogs that did not return "
        "rule text are candidates there, not adapters."
    ),
}

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
    path = ROOT / "data" / "SOURCES.md"
    lines = [
        "# Data sources",
        "",
        "Data files: `data/processed/*.json` and `*.geojson` are committed. `make ingest` builds them through a gitignored SQLite cache at `data/raw/ingest.sqlite`. Production database is `TODO_HUMAN` in `config/decisions.yaml`. Raw responses are cached under `data/raw/` (gitignored).",
        "",
        "Article bodies are not stored. GLIDE comments and IDMC notes are clipped to 280 characters.",
        "",
        "ReliefWeb is not an active source: `api.reliefweb.int` robots.txt disallows `/v2/`, and the API requires a pre-approved appname. No ReliefWeb request is sent.",
        "",
        "DDPM situation reports were not added. The repo owner took DDPM out of this run.",
        "",
        "## Do not collect",
        "",
    ]
    for item in DO_NOT_COLLECT:
        lines.append(f"- {item}")
    lines.extend(["", "## Fetched this run", ""])
    if not store.available():
        lines.append("No data yet. Run `make ingest`.")
        lines.append("")
    else:
        status_rows = sorted(store.rows("source_status"), key=lambda r: r["source"])
        flood_counts: dict[str, int] = {}
        for props, _ in store.flood_shapes():
            layer = props.get("layer") or ""
            flood_counts[layer] = flood_counts.get(layer, 0) + 1
        counts = {
            "flood_extent": flood_counts.get("flood_extent", 0),
            "repeat_flood": flood_counts.get("repeat_flood", 0),
            "disaster_report": len(store.rows("disaster_report")),
            "weather_observation": len(store.rows("weather_observation")),
            "infrastructure": len(store.facilities()),
            "districts": len(store.rows("districts")),
            "admin_districts": len(store.rows("admin_districts")),
        }
        lines.append("| table | rows |")
        lines.append("|---|---|")
        for name, count in counts.items():
            lines.append(f"| {name} | {count} |")
        lines.extend(["", "| source | status | rows | fetched_at | detail |", "|---|---|---|---|---|"])
        candidates = []
        for row in status_rows:
            if row["status"] == "candidate":
                candidates.append(row)
                continue
            detail = " ".join(str(row["detail"] or "").split())
            lines.append(
                f"| {row['source']} | {row['status']} | {row['row_count']} | {row['fetched_at']} | {detail} |"
            )
        lines.extend(["", "## HDX candidates not fetched", ""])
        if not candidates:
            lines.append("None recorded.")
        else:
            lines.append("| dataset | detail |")
            lines.append("|---|---|")
            for row in candidates:
                detail = " ".join(str(row["detail"] or "").split())
                lines.append(f"| {row['source']} | {detail} |")
        lines.append("")
    lines.extend(["## Later — human to approve", ""])
    for name in LATER:
        lines.append(f"- {name}: {LATER_NOTES.get(name, 'later — human to approve. Not fetched.')}")
    lines.append("")
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write_sources())
