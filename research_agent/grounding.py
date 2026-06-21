"""Grounding verification.

After synthesis, every claim in the answer is checked against the retrieved
sources. With a provider, this uses LLM-based claim extraction + entailment
(llm_grounding.py); without one (offline / CI) it falls back to the lexical
heuristic in mcp_server.tools. Either way the output is a GroundingReport
("X of Y claims verified") plus the flagged (unsupported) claims, so ungrounded
statements are surfaced rather than shipped silently.
"""

from __future__ import annotations

from core.providers import Provider
from core.types import GroundingReport, Source
from mcp_server import tools

from . import llm_grounding


def verify_answer(answer_text: str, sources: list[Source], provider: Provider | None = None,
                  threshold: float = 0.35) -> GroundingReport:
    if provider is not None:
        claims = llm_grounding.llm_extract_claims(provider, answer_text)
        report = GroundingReport()
        for claim in claims:
            report.results.append(llm_grounding.llm_check_grounding(provider, claim.text, sources))
        return report

    # Offline fallback: lexical extraction + containment.
    claims = tools.extract_claims(answer_text)
    report = GroundingReport()
    for claim in claims:
        report.results.append(tools.check_grounding(claim.text, sources, threshold=threshold))
    return report


def annotate_flagged(answer_text: str, report: GroundingReport) -> str:
    """Append a transparency footer listing claims that couldn't be grounded."""
    flagged = report.flagged
    if not flagged:
        return answer_text + "\n\n> Grounding: " + report.summary() + "."
    lines = [answer_text, "", f"> Grounding: {report.summary()}.",
             "> The following statements could not be verified against the sources "
             "and should be treated with caution:"]
    for r in flagged:
        lines.append(f"> - {r.claim}")
    return "\n".join(lines)
