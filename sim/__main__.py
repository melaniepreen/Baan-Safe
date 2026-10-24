"""Run the stub caller environment. `make sim-eval`."""

from __future__ import annotations

from sim.callers.catalog import CATALOG
from sim.coach import write_jsonl
from sim.env import run_episode
from sim.report import render
from paths import ROOT


def main() -> int:
    from eval.learning.simulators import render_trait_section

    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    episodes = [run_episode(spec) for spec in CATALOG]
    coach_path = out / "coach.jsonl"
    count = write_jsonl(episodes, coach_path)
    text = render(episodes, count).rstrip() + "\n\n" + render_trait_section()
    path = out / "sim.md"
    path.write_text(text, encoding="utf-8")
    print(path)
    print("stub caller environment; not a measured result")
    print("sim.caller_model=TODO_HUMAN sim.caller_gpu=TODO_HUMAN")
    print(f"coach={coach_path} rows={count} source=coach promoted=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
