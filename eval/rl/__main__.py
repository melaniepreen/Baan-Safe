"""`python -m eval.rl --s2 live|replay|fake [--epochs N] [--seed N]`."""

from __future__ import annotations

import argparse

from config.envfile import load_env_file
from eval.rl.run import run


def main() -> int:
    parser = argparse.ArgumentParser(description="BaanSafe RL loop")
    parser.add_argument("--s2", choices=("live", "replay", "fake"), default="replay")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    load_env_file()
    payload = run(s2=args.s2, epochs=args.epochs, seed=args.seed)
    for epoch in payload["epochs"]:
        print(
            f"epoch {epoch['epoch']}: episodes={epoch['episodes']} "
            f"mean_reward={epoch['mean_reward']} correct={epoch['correct']} "
            f"under_triage={epoch['under_triage']} "
            f"critical_under={epoch['critical_under']} "
            f"s1={epoch['share_s1_only']} cascade={epoch['share_cascade']} "
            f"s2={epoch['share_s2_only']} fallbacks={epoch['s2_fallbacks']}"
        )
    kinds: dict[str, int] = {}
    for event in payload["events"]:
        kinds[event["kind"]] = kinds.get(event["kind"], 0) + 1
    print(
        "events: "
        + (", ".join(f"{kind}={count}" for kind, count in sorted(kinds.items())) or "none")
    )
    print(f"overlay: graduated={len(payload['final_overlay']['graduated'])} "
          f"recommendations={len(payload['final_overlay']['recommendations'])} "
          f"demoted={len(payload['final_overlay']['demoted'])}")
    print(f"training: {payload['training']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
