"""Grounding verification.

After synthesis, every claim in the answer is checked against the retrieved
sources. The output is a GroundingReport ("X of Y claims verified") plus the
list of flagged (unsupported) claims, so ungrounded statements are surfaced —
flagged or dropped — rather than shipped silently.
"""

from __future__ import annotations

from core.types import GroundingReport, Source
from mcp_server import tools


def verify_answer(answer_text: str, sources: list[Source], threshold: float = 0.35) -> GroundingReport:
    """Extract claims from the answer and check each against the sources."""
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
