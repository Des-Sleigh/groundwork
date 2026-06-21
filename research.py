"""Real research CLI — runs the orchestrator against live models.

This is the entry point for a real run (vs. run_demo.py, which is offline/mock).
It uses the default TieredRouter (routes to Anthropic) and the configured search
backend (Tavily if TAVILY_API_KEY is set, else the local fixture corpus).

    export ANTHROPIC_API_KEY=sk-ant-...
    export TAVILY_API_KEY=tvly-...        # optional, for live web search
    python research.py "How are mid-market logistics firms using AI for demand forecasting?"

Writes the cited brief to reports/ and prints the grounding report, injection
flags, and per-role cost breakdown.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.loop import Orchestrator

ROOT = Path(__file__).resolve().parent
DEFAULT_Q = ("How are mid-market logistics firms using AI for demand forecasting, "
             "and what ROI evidence exists?")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    question = " ".join(argv) if argv else DEFAULT_Q

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set. This is the REAL run; set a key, "
              "or use `python run_demo.py` for the offline mock demo.", file=sys.stderr)
        return 2

    orch = Orchestrator()  # default tiers: planner/critic=sonnet, workers=haiku
    result = orch.run(question)

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Deduplicated source pool actually consulted across workers.
    seen, sources = set(), []
    for w in result.get("worker_results", []):
        for s in w.get("sources", []):
            if s.get("url") and s["url"] not in seen:
                seen.add(s["url"])
                sources.append(s)

    md = ["# Research brief\n", f"**Question:** {question}\n", result["answer"], ""]
    fg = result.get("final_grounding")
    if fg:
        md += ["## Grounding", f"- {fg['summary']} (final synthesized answer, "
               "re-verified against the source pool)."]
    if sources:
        md += ["", "## Sources consulted", ""]
        md += [f"{i}. [{s.get('title') or s['url']}]({s['url']})" for i, s in enumerate(sources, 1)]
    md += ["", "## Run metadata", f"- Sub-tasks: {result['n_tasks']}, accepted: {result['n_accepted']}, "
           f"revised: {result['n_revised']}, rejected: {result['rejected_tasks']}",
           "", "### Cost by role", "```", result["cost_render"], "```"]
    brief_path = reports / f"research_brief_{stamp}.md"
    brief_path.write_text("\n".join(md))
    (reports / f"trace_{stamp}.json").write_text(json.dumps(result["trace"], indent=2, default=str))

    print(result["answer"])
    print("\n--- cost by role ---\n" + result["cost_render"])
    print(f"\nWrote {brief_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
