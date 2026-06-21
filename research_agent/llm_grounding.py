"""LLM-based claim extraction and grounding (entailment).

This is the "real" grounding path. Instead of lexical word-overlap, a model:
  - extract_claims: splits an answer into atomic, checkable factual claims
  - check_grounding: decides whether a claim is *entailed* by the sources,
    returning the supporting source, an evidence quote, and a confidence

Both return strict JSON, parsed defensively. When no provider is available
(offline / CI), callers fall back to the lexical heuristic in mcp_server.tools,
so the pipeline always runs.
"""

from __future__ import annotations

from core.providers import Provider
from core.types import Claim, GroundingResult, Source
from core.util import extract_json, get_logger

log = get_logger(__name__)

_EXTRACT_SYSTEM = (
    "You split text into atomic factual claims. A claim is a single, "
    "independently-checkable assertion. Ignore questions, opinions, and hedges. "
    'Return ONLY JSON: {"claims": ["claim 1", "claim 2", ...]}.'
)

_GROUND_SYSTEM = (
    "You are a strict grounding verifier. Decide whether a CLAIM is supported "
    "(entailed) by the provided SOURCES. A claim is supported only if a source "
    "directly states or clearly implies it — not merely related topics. "
    'Return ONLY JSON: {"supported": true|false, "source_index": <int or null>, '
    '"evidence": "<short quote from that source, or empty>", '
    '"confidence": <0.0-1.0>}.'
)


def llm_extract_claims(provider: Provider, text: str, max_claims: int = 20) -> list[Claim]:
    out = provider.generate(f"Text:\n{text}\n\nExtract the atomic claims.",
                            system=_EXTRACT_SYSTEM, max_tokens=1024)
    obj = extract_json(out.text)
    items = obj.get("claims", []) if isinstance(obj, dict) else []
    claims = [Claim(text=str(c).strip(), id=f"c{i + 1}") for i, c in enumerate(items) if str(c).strip()]
    return claims[:max_claims]


def llm_check_grounding(provider: Provider, claim: str, sources: list[Source]) -> GroundingResult:
    if not sources:
        return GroundingResult(claim=claim, supported=False, best_source_url=None, evidence="", score=0.0)

    numbered = "\n\n".join(f"[{i}] {s.title}\n{s.text[:1500]}" for i, s in enumerate(sources))
    prompt = f"CLAIM:\n{claim}\n\nSOURCES:\n{numbered}\n\nIs the claim supported?"
    out = provider.generate(prompt, system=_GROUND_SYSTEM, max_tokens=400)
    obj = extract_json(out.text)

    if not isinstance(obj, dict):
        log.warning("grounding verdict unparseable for claim: %s", claim[:60])
        return GroundingResult(claim=claim, supported=False, best_source_url=None,
                               evidence="(verdict unparseable)", score=0.0)

    idx = obj.get("source_index")
    url = None
    if isinstance(idx, int) and 0 <= idx < len(sources):
        url = sources[idx].url
    try:
        score = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
    except (TypeError, ValueError):
        score = 0.0
    return GroundingResult(
        claim=claim,
        supported=bool(obj.get("supported", False)),
        best_source_url=url,
        evidence=str(obj.get("evidence", ""))[:300],
        score=round(score, 3),
    )
