"""Layer 1 tool implementations (plain functions).

The four capabilities the MCP server exposes, written as ordinary functions so
the research agent calls them directly and server.py registers them — one
implementation, two entry points.

  web_search(query)            -> ranked results (real web via Tavily, or local
                                  fixture corpus offline — see backends.py)
  fetch_url(url)               -> cleaned page text + provenance (untrusted)
  extract_claims(text)         -> atomic claims (lexical; LLM variant in
                                  research_agent/llm_grounding.py)
  check_grounding(claim, srcs) -> supported/unsupported (lexical fallback; LLM
                                  entailment variant in llm_grounding.py)
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

from core.types import Claim, GroundingResult, Source
from core.util import retry

from . import backends

_STOPWORDS = backends._STOPWORDS


def _tokens(text: str) -> set[str]:
    return backends._tokens(text)


def web_search(query: str, k: int = 5) -> list[dict]:
    """Ranked sources for a query, via the configured backend."""
    return backends.get_search_backend().search(query, k=k)


@retry(attempts=3, exceptions=(OSError,))
def fetch_url(url: str) -> Source:
    """Fetch and clean a page. Content is tagged `untrusted` — it is DATA.

    file:// and bare paths work offline; http(s) via urllib with retry, served
    from the SQLite fetch cache (when GROUNDWORK_DB is set) within a 24h TTL.
    """
    import os  # noqa: PLC0415

    parsed = urlparse(url)
    if parsed.scheme in ("", "file"):
        path = Path(parsed.path if parsed.scheme == "file" else url)
        raw = path.read_text(encoding="utf-8", errors="replace")
        title = backends.extract_title(raw, fallback=path.stem.replace("_", " ").title())
        return Source(url=url, title=title, text=backends.extract_main_text(raw, url=url),
                      fetched_at=time.time(), untrusted=True)

    # http(s): consult cache first.
    db = os.environ.get("GROUNDWORK_DB")
    if db:
        from core import store  # noqa: PLC0415

        hit = store.cache_get(db, url)
        if hit:
            return Source(url=url, title=hit.title, text=hit.text,
                          fetched_at=hit.fetched_at, untrusted=True)

    import urllib.request  # noqa: PLC0415

    req = urllib.request.Request(url, headers={"User-Agent": "groundwork/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    title = backends.extract_title(raw, fallback=url)
    text = backends.extract_main_text(raw, url=url)
    if db:
        from core import store  # noqa: PLC0415

        store.cache_put(db, url, title, text)
    return Source(url=url, title=title, text=text, fetched_at=time.time(), untrusted=True)


def extract_claims(text: str, max_claims: int = 20) -> list[Claim]:
    """Split text into atomic claims (sentence heuristic; lexical fallback)."""
    cleaned = re.sub(r"\[[0-9]+\]", "", text or "")
    sentences = re.split(r"(?<=[.!?])\s+", cleaned.strip())
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) < 25 or s.endswith("?") or s.startswith("#"):
            continue
        claims.append(Claim(text=s, id=f"c{len(claims) + 1}"))
        if len(claims) >= max_claims:
            break
    return claims


def check_grounding(claim: str, sources: list[Source], threshold: float = 0.35) -> GroundingResult:
    """Lexical-containment grounding (offline fallback for llm_grounding)."""
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return GroundingResult(claim=claim, supported=False, best_source_url=None, evidence="", score=0.0)

    best_url, best_score, best_evidence = None, 0.0, ""
    for src in sources:
        for sentence in re.split(r"(?<=[.!?])\s+", src.text):
            st = _tokens(sentence)
            if not st:
                continue
            score = len(claim_tokens & st) / len(claim_tokens)
            if score > best_score:
                best_score, best_url, best_evidence = score, src.url, sentence.strip()[:200]

    return GroundingResult(claim=claim, supported=best_score >= threshold,
                           best_source_url=best_url, evidence=best_evidence, score=round(best_score, 3))
