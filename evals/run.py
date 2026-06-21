"""Evaluate Groundwork's own differentiators and write a report.

Measures the two safety-critical behaviors against labeled datasets:

  - grounding accuracy: does check_grounding correctly judge whether a claim is
    supported by its sources? (precision / recall / F1 / accuracy)
  - injection resistance (detection layer): does scan_for_injection correctly
    flag manipulation attempts while leaving clean content alone?

The grounding eval runs the lexical heuristic with no key (so CI + this repo can
commit real numbers). If ANTHROPIC_API_KEY is set, it ALSO runs the LLM
entailment grounder and reports both — quantifying the upgrade.

    python -m evals.run            # writes evals/report.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.types import Source
from mcp_server import tools
from research_agent.defenses import scan_for_injection

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "datasets"


def _metrics(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs of (pred, gold) for the positive class -> P/R/F1/accuracy."""
    tp = sum(1 for p, g in pairs if p and g)
    fp = sum(1 for p, g in pairs if p and not g)
    fn = sum(1 for p, g in pairs if not p and g)
    tn = sum(1 for p, g in pairs if not p and not g)
    n = len(pairs)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    accuracy = (tp + tn) / n if n else None
    return {"n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy}


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line.strip()]


def eval_grounding_lexical() -> dict:
    pairs = []
    for case in _load("grounding.jsonl"):
        srcs = [Source(url=f"s{i}", title=s["title"], text=s["text"])
                for i, s in enumerate(case["sources"])]
        pred = tools.check_grounding(case["claim"], srcs).supported
        pairs.append((pred, bool(case["supported"])))
    return _metrics(pairs)


def eval_grounding_llm() -> dict | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from core.providers import AnthropicProvider  # noqa: PLC0415
    from research_agent import llm_grounding  # noqa: PLC0415

    provider = AnthropicProvider("claude-sonnet-4-6")
    pairs = []
    for case in _load("grounding.jsonl"):
        srcs = [Source(url=f"s{i}", title=s["title"], text=s["text"])
                for i, s in enumerate(case["sources"])]
        pred = llm_grounding.llm_check_grounding(provider, case["claim"], srcs).supported
        pairs.append((pred, bool(case["supported"])))
    return _metrics(pairs)


def eval_injection() -> dict:
    pairs = []
    for case in _load("injection.jsonl"):
        if "file" in case:
            text = tools.fetch_url((ROOT / case["file"]).as_uri()).text
        else:
            text = case["text"]
        pred = scan_for_injection(text).suspicious
        pairs.append((pred, bool(case["suspicious"])))
    return _metrics(pairs)


def _row(name: str, m: dict) -> str:
    def f(x):
        return "—" if x is None else f"{x:.2f}"
    return (f"| {name} | {m['n']} | {f(m['precision'])} | {f(m['recall'])} | "
            f"{f(m['f1'])} | {f(m['accuracy'])} |")


def main() -> int:
    lex = eval_grounding_lexical()
    llm = eval_grounding_llm()
    inj = eval_injection()

    lines = ["# Groundwork evaluation report", ""]
    lines.append("Measures Groundwork's grounding accuracy and injection-detection "
                 "on labeled datasets. The lexical grounder and the regex injection "
                 "detector need no API key, so these numbers are reproducible in CI.")
    lines.append("")
    lines.append("## Grounding accuracy (claim supported by sources?)")
    lines.append("")
    lines.append("| Method | n | Precision | Recall | F1 | Accuracy |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(_row("lexical heuristic", lex))
    if llm:
        lines.append(_row("LLM entailment (claude-sonnet-4-6)", llm))
    else:
        lines.append("| LLM entailment | — | — | — | — | _set ANTHROPIC_API_KEY to measure_ |")
    lines.append("")
    lines.append("## Injection detection (manipulation attempt flagged?)")
    lines.append("")
    lines.append("| Method | n | Precision | Recall | F1 | Accuracy |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(_row("regex pattern scan", inj))
    lines.append("")
    lines.append("> Datasets: `evals/datasets/`. Re-run with `python -m evals.run`.")
    lines.append("")

    out = Path(__file__).resolve().parent / "report.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
