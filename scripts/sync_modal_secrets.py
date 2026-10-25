"""Push gitignored .env keys into Modal secrets. Never print values.

Reads .env (or BAANSAFE_ENV), creates/updates:
  baansafe-hf    <- HF_TOKEN
  baansafe-mubit <- MUBIT_API_KEY, MUBIT_BASE_URL, and optional
                    S2_SERVE_API_KEY, MUBIT_PROJECT_ID, MUBIT_CONTROL_URL

llm/client.py refuses without both Mubit values, so both are required.

OPENROUTER_API_KEY is not synced. System 2 goes through Mubit.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_SPECS = (
    ("baansafe-hf", ("HF_TOKEN",), ("HF_TOKEN",)),
    (
        "baansafe-mubit",
        ("MUBIT_API_KEY", "MUBIT_BASE_URL"),
        (
            "MUBIT_API_KEY",
            "MUBIT_BASE_URL",
            "S2_SERVE_API_KEY",
            "MUBIT_PROJECT_ID",
            "MUBIT_CONTROL_URL",
        ),
    ),
)


def env_path() -> Path:
    override = os.environ.get("BAANSAFE_ENV", "").strip()
    return Path(override) if override else ROOT / ".env"


def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"missing {path}; copy .env.example to .env and fill keys")
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def sync_one(secret_name: str, required: tuple[str, ...], optional: tuple[str, ...], keys: dict[str, str]) -> None:
    missing = [k for k in required if not keys.get(k)]
    if missing:
        raise SystemExit(f"{secret_name}: set {', '.join(missing)} in .env")
    names = tuple(k for k in optional if keys.get(k))
    # Pass KEY=value to modal; do not use --from-dotenv (needs python-dotenv and
    # would upload the whole .env). Never print the values.
    keyvalues = [f"{name}={keys[name]}" for name in names]
    subprocess.run(
        ["modal", "secret", "create", secret_name, *keyvalues, "--force"],
        check=True,
        cwd=ROOT,
    )
    print(f"synced {secret_name} ({', '.join(names)})")


def main() -> int:
    keys = parse_dotenv(env_path())
    for secret_name, required, optional in SECRET_SPECS:
        sync_one(secret_name, required, optional, keys)
    return 0


if __name__ == "__main__":
    sys.exit(main())
