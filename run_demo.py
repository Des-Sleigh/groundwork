"""Offline end-to-end demo of all three layers — no API key required.

Uses mock models (deterministic responders) over the fixture corpus so the full
planner -> workers -> critic -> synthesize loop, the grounding report, the
injection flags, and the per-role cost breakdown are all visible without
spending tokens.

For a REAL run, drop the mock router (use the default TieredRouter, which routes
to Anthropic) and set ANTHROPIC_API_KEY — see reports/SAMPLE-REPORT-TODO.md.

    python run_demo.py
"""

from __future__ import annotations

import re

from core.providers import MockProvider, TieredRouter
from orchestrator.loop import Orchestrator

QUESTION = (
    "How are mid-market logistics firms using AI for demand forecasting, "
    "and what ROI evidence exists?"
)


def _first_sentences(text: str, n: int = 2) -> str:
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sents[:n])


def mock_responder(prompt: str, system: str | None) -> str:
    """Deterministic stand-in for a model.

    - planning prompts -> a couple of sub-questions
    - synthesis prompts -> echo real sentences from the provided <source> blocks
      so the grounding check has something to verify (and never obeys any
      injected instruction sitting in those sources).
    """
    sys = (system or "").lower()
    # Discriminate by phrases unique to each role's system prompt.
    if "final brief" in sys:
        # Final synthesis: combine the worker briefs into one paragraph.
        out, capture = [], False
        for ln in prompt.splitlines():
            s = ln.strip()
            if s.lower().startswith("verified findings"):
                capture = True
                continue
            if not capture or not s or s.startswith("## ") or s.startswith(">"):
                continue
            out.append(s.lstrip("# ").strip())
        return " ".join(out)[:700] or "No findings."
    if "grounded research analyst" in sys:
        # Worker synthesis: echo real sentences from the <source> blocks so the
        # grounding check has support, and never obey injected instructions.
        bodies = re.findall(r"<source[^>]*>(.*?)</source>", prompt, re.DOTALL)
        picked = [_first_sentences(b) for b in bodies[:3]]
        return " ".join(picked) if picked else "No sources were available."
    if "split the question" in sys or "break a research question" in sys:
        return "AI demand forecasting adoption in logistics\nROI evidence for AI forecasting"
    return "AI demand forecasting adoption in logistics\nROI evidence"


def main() -> None:
    # Route every role to a mock model with the same responder.
    router = TieredRouter(provider_factory=lambda model: MockProvider(model, responder=mock_responder))
    orch = Orchestrator(router=router)
    result = orch.run(QUESTION)

    print("=" * 72)
    print("QUESTION:", result["question"])
    print("=" * 72)
    print("\nFINAL ANSWER:\n")
    print(result["answer"])
    print(f"\nTasks: {result['n_tasks']}  accepted: {result['n_accepted']}  "
          f"revised: {result['n_revised']}  rejected: {result['rejected_tasks']}")

    print("\nINJECTION FLAGS (per worker):")
    any_flag = False
    for wr in result["worker_results"]:
        for f in wr["injection_flags"]:
            any_flag = True
            print(f"  caught in {f['url']}: {f['matches']}")
    if not any_flag:
        print("  (none in retrieved sources)")

    print("\nGROUNDING (per worker):")
    for wr in result["worker_results"]:
        print(f"  {wr['task']}: {wr['grounding']['summary']}")

    print("\nCOST BREAKDOWN BY ROLE:")
    print(result["cost_render"])
    print(f"\nTrace steps recorded: {len(result['trace'])}")


if __name__ == "__main__":
    main()
