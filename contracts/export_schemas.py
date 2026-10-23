"""Export each contract model to contracts/schemas/<Name>.json."""

from __future__ import annotations

import json
from enum import Enum

from contracts.models import MODEL_TYPES
from paths import ROOT

SCHEMA_DIR = ROOT / "contracts" / "schemas"


def export_schemas() -> list[str]:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for model in MODEL_TYPES:
        if isinstance(model, type) and issubclass(model, Enum):
            schema = {
                "title": model.__name__,
                "description": model.__doc__ or "",
                "type": "string",
                "enum": [member.value for member in model],
            }
        else:
            schema = model.model_json_schema()
            schema["title"] = model.__name__
        path = SCHEMA_DIR / f"{model.__name__}.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(path.name)
    return written


if __name__ == "__main__":
    names = export_schemas()
    print(f"wrote {len(names)} schemas to {SCHEMA_DIR}")
