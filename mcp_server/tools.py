"""Layer 1 tool implementations (plain functions).

These are the four capabilities the MCP server exposes. They're written as
ordinary functions so the research agent can call them directly *and* the MCP
server (server.py) can register them — one implementation, two entry points.

  web_search(query)            -> ranked results
  fetch_url(url)               -> cleaned page text + provenance (untrusted)
  extract_claims(text)         -> list of atomic claims
  check_grounding(claim, srcs) -> supported / unsupported + which source

Fetching/search default to a local fixture corpus so the whole pipeline (and
the injection red-team suite) runs offline and deterministically. Point
`GROUNDWORK_CORPUS` at a directory, or wire a real search/HTTP backend, for
live research.
"""

from __future__ import annotations

import html
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from core.types import Claim, GroundingResult, Source

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "is",
    "are", "was", "were", "be", "been", "with", "as", "by", "at", "from", "that",
    "this", "it", "its", "their", "they", "has", "have", "had", "will", "can",
    "into", "than", "then", "so", "such", "we", "you", "i", "not", "no",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOPWORDS and len(w) > 2}


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def corpus_dir() -> Path:
    env = os.environ.get("GROUNDWORK_CORPUS")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _corpus_files() -> list[Path]:
    """Files the offline search/fetch may retrieve.

    With GROUNDWORK_CORPUS set, search that directory wholesale. Otherwise scope
    to the repo's `corpus/` (fixture docs) and `redteam/` (injection canaries)
    so ordinary source/README files aren't treated as retrievable sources.
    """
    root = corpus_dir()
    exts = {".txt", ".md", ".html", ".htm"}
    if os.environ.get("GROUNDWORK_CORPUS"):
        roots = [root]
    else:
        roots = [root / "corpus", root / "redteam"]
    files: list[Path] = []
    for base in roots:
        if base.exists():
            files.extend(p for p in base.rglob("*") if p.suffix.lower() in exts and p.is_file())
    return files


def web_search(query: str, k: int = 5) -> list[dict]:
    """Rank local corpus documents by keyword overlap with the query.

    Returns [{url, title, score}]. Swap this body for a real search API
    (Tavily/Brave/Bing/Anthropic web_search) without touching callers.
    """
    q = _tokens(query)
    scored = []
    for path in _corpus_files():
        try:
            text = _strip_html(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        overlap = len(q & _tokens(text))
        if overlap:
            scored.append((overlap, path, text))
    scored.sort(key=lambda t: t[0], reverse=True)
    results = []
    for overlap, path, text in scored[:k]:
        results.append({
            "url": path.as_uri(),
            "title": path.stem.replace("_", " ").title(),
            "score": overlap,
            "snippet": text[:160],
        })
    return results


def fetch_url(url: str) -> Source:
    """Fetch and clean a page. Content is tagged `untrusted` — it is DATA.

    Supports file:// and local paths offline; http(s) via urllib when reachable.
    """
    parsed = urlparse(url)
    if parsed.scheme in ("", "file"):
        path = Path(parsed.path if parsed.scheme == "file" else url)
        raw = path.read_text(encoding="utf-8", errors="replace")
        title = path.stem.replace("_", " ").title()
    else:
        import urllib.request  # noqa: PLC0415 — lazy; offline path needs no network

        req = urllib.request.Request(url, headers={"User-Agent": "groundwork/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
        m = re.search(r"(?is)<title>(.*?)</title>", raw)
        title = _strip_html(m.group(1)) if m else url

    return Source(url=url, title=title, text=_strip_html(raw), fetched_at=time.time(), untrusted=True)


def extract_claims(text: str, max_claims: int = 20) -> list[Claim]:
    """Split synthesized text into atomic, checkable claims (sentence heuristic).

    A model-backed extractor can replace this; the agent uses the result the
    same way either way.
    """
    # Drop bracketed citation markers like [1] before splitting.
    cleaned = re.sub(r"\[[0-9]+\]", "", text or "")
    sentences = re.split(r"(?<=[.!?])\s+", cleaned.strip())
    claims = []
    for s in sentences:
        s = s.strip()
        # Skip headers, questions, and trivially short fragments.
        if len(s) < 25 or s.endswith("?") or s.startswith("#"):
            continue
        claims.append(Claim(text=s, id=f"c{len(claims) + 1}"))
        if len(claims) >= max_claims:
            break
    return claims


def check_grounding(claim: str, sources: list[Source], threshold: float = 0.35) -> GroundingResult:
    """Is `claim` supported by any source? Lexical-containment heuristic.

    Scores each source by how much of the claim's content vocabulary appears in
    it, picks the best, and marks supported if it clears `threshold`. A
    model-backed entailment check can be slotted in behind the same signature.
    """
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return GroundingResult(claim=claim, supported=False, best_source_url=None, evidence="", score=0.0)

    best_url, best_score, best_evidence = None, 0.0, ""
    for src in sources:
        # Score against the best-matching sentence window for readable evidence.
        for sentence in re.split(r"(?<=[.!?])\s+", src.text):
            st = _tokens(sentence)
            if not st:
                continue
            score = len(claim_tokens & st) / len(claim_tokens)
            if score > best_score:
                best_score, best_url, best_evidence = score, src.url, sentence.strip()[:200]

    return GroundingResult(
        claim=claim,
        supported=best_score >= threshold,
        best_source_url=best_url,
        evidence=best_evidence,
        score=round(best_score, 3),
    )
