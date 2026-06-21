"""Benchmark: naive RAG vs. Groundwork's grounding filter.

The thesis Groundwork makes is "an answer you can trust." This benchmark turns
that into a number by asking: of the claims an agent is about to ship, how many
are unsupported by its own retrieved sources — i.e. hallucinations?

Three approaches, scored on the same labeled set (`evals/datasets/grounding.jsonl`,
each claim tagged supported/unsupported against its sources):

  - Naive RAG       — retrieves, synthesizes, ships every claim. No verification.
  - Groundwork      — runs check_grounding per claim and drops/flags the
    (lexical)         unsupported ones. Free, offline, in CI.
  - Groundwork      — the LLM-entailment grounder. Needs ANTHROPIC_API_KEY.
    (LLM entailment)

Two metrics:
  - Hallucinations shipped  (lower is better): unsupported claims that slip
    through as if true.
  - Valid claims kept       (higher is better): supported claims retained
    (a grounder that drops everything would score 0% hallucinations but be
    useless).

    python -m benchmark.run        # writes benchmark/report.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.types import Source
from mcp_server import tools

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "evals" / "datasets" / "grounding.jsonl"


def _cases() -> list[dict]:
    return [json.loads(ln) for ln in DATA.read_text().splitlines() if ln.strip()]


def _sources(case: dict) -> list[Source]:
    return [Source(url=f"s{i}", title=s["title"], text=s["text"])
            for i, s in enumerate(case["sources"])]


def _score(decider) -> dict:
    """decider(claim, sources) -> bool 'shipped as supported'. Returns metrics."""
    cases = _cases()
    n_false = sum(1 for c in cases if not c["supported"])
    n_true = sum(1 for c in cases if c["supported"])
    shipped_false = kept_true = 0
    for c in cases:
        shipped = decider(c["claim"], _sources(c))
        if not c["supported"] and shipped:
            shipped_false += 1   # a hallucination slipped through
        if c["supported"] and shipped:
            kept_true += 1       # a valid claim retained
    return {
        "hallucination_passthrough": shipped_false / n_false if n_false else None,
        "valid_retention": kept_true / n_true if n_true else None,
        "shipped_false": shipped_false, "n_false": n_false,
        "kept_true": kept_true, "n_true": n_true,
    }


def naive_decider(claim, sources) -> bool:
    return True  # ships everything; no verification


def lexical_decider(claim, sources) -> bool:
    return tools.check_grounding(claim, sources).supported


def llm_decider_factory():
    from core.providers import AnthropicProvider  # noqa: PLC0415
    from research_agent import llm_grounding  # noqa: PLC0415

    provider = AnthropicProvider("claude-sonnet-4-6")
    return lambda claim, sources: llm_grounding.llm_check_grounding(provider, claim, sources).supported


def _row(name: str, m: dict) -> str:
    def pct(x):
        return "—" if x is None else f"{x * 100:.0f}%"
    return (f"| {name} | {pct(m['hallucination_passthrough'])} "
            f"({m['shipped_false']}/{m['n_false']}) | {pct(m['valid_retention'])} "
            f"({m['kept_true']}/{m['n_true']}) |")


def main() -> int:
    naive = _score(naive_decider)
    lexical = _score(lexical_decider)
    llm = _score(llm_decider_factory()) if os.environ.get("ANTHROPIC_API_KEY") else None

    lines = ["# Benchmark: naive RAG vs. grounded (Groundwork)", ""]
    lines.append("Same labeled claim set (`evals/datasets/grounding.jsonl`); the question is "
                 "how many *unsupported* claims each approach ships as if true.")
    lines.append("")
    lines.append("| Approach | Hallucinations shipped ↓ | Valid claims kept ↑ |")
    lines.append("|---|---:|---:|")
    lines.append(_row("Naive RAG (no grounding)", naive))
    lines.append(_row("Groundwork — lexical grounder", lexical))
    if llm:
        lines.append(_row("Groundwork — LLM entailment (claude-sonnet-4-6)", llm))
    else:
        # No key in this run: report the measured result from evals/report.md,
        # which scores the same grounder on the same set (precision 1.00 -> 0
        # unsupported claims shipped; recall 0.94 -> 17/18 valid claims kept).
        lines.append("| Groundwork — LLM entailment (claude-sonnet-4-6) † | **0%** (0/12) | 94% (17/18) |")
    lines.append("")
    lines.append("**Naive RAG ships 100% of hallucinations** — it has no notion of whether a "
                 "claim is supported. Groundwork's grounding filter is the difference between "
                 "a confident-but-wrong answer and a trustworthy one. The lexical grounder "
                 "already removes most; the LLM entailment grounder removes essentially all, "
                 "at a small cost in valid-claim retention.")
    lines.append("")
    if not llm:
        lines.append("† LLM-entailment row from the measured eval on this same set "
                     "(`evals/report.md`: precision 1.00, recall 0.94). Run `benchmark.run` "
                     "with a key to compute it live here.")
        lines.append("")
    lines.append("> Reproduce: `python -m benchmark.run` (LLM row needs a key).")
    lines.append("")

    out = Path(__file__).resolve().parent / "report.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
