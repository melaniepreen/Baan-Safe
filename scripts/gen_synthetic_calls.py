"""Write fixtures/synthetic. Seeded, no network, no model.

    python3 scripts/gen_synthetic_calls.py
"""

from __future__ import annotations

import json

from fixtures.synthetic_build import SEED, label_counts, write_catalog


def main() -> None:
    catalog = write_catalog()
    held = set(catalog["held_out_groups"])
    train_calls = sum(1 for call in catalog["calls"] if call["group_id"] not in held)
    held_calls = len(catalog["calls"]) - train_calls
    print(f"seed {SEED}")
    print(f"calls {len(catalog['calls'])}")
    print(f"groups train {len(catalog['train_groups'])} held_out {len(catalog['held_out_groups'])}")
    print(f"calls train {train_calls} held_out {held_calls}")
    print("label positives " + json.dumps(label_counts(catalog["calls"]), sort_keys=True))
    print("demo " + " ".join(catalog["demo_ids"]))


if __name__ == "__main__":
    main()
