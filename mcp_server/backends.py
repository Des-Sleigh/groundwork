"""Pluggable search + fetch backends.

The agent doesn't care where sources come from — it calls `web_search` /
`fetch_url` in tools.py, which delegate to the configured backend here. This is
where "real" plugs in:

  - SearchBackend: Tavily (real web) or LocalCorpus (offline fixtures / CI)
  - extract_main_text: trafilatura -> BeautifulSoup -> regex, best available

Selection is automatic: if GROUNDWORK_SEARCH_BACKEND is set, honor it; else use
Tavily when TAVILY_API_KEY is present, otherwise the local corpus. This keeps
CI and offline dev working with zero keys while flipping to real web research
the moment a key exists.
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path

from core.util import get_logger, retry

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# HTML -> text extraction
# --------------------------------------------------------------------------- #

def _regex_strip(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|header).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def extract_main_text(raw_html: str, url: str = "") -> str:
    """Extract readable main text, using the best library available."""
    # 1) trafilatura — best at stripping boilerplate.
    try:
        import trafilatura  # noqa: PLC0415

        extracted = trafilatura.extract(raw_html, url=url or None, include_comments=False)
        if extracted and len(extracted) > 80:
            return extracted.strip()
    except Exception:  # noqa: BLE001
        pass
    # 2) BeautifulSoup — decent fallback.
    try:
        from bs4 import BeautifulSoup  # noqa: PLC0415

        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ")
        return re.sub(r"\s+", " ", text).strip()
    except Exception:  # noqa: BLE001
        pass
    # 3) regex — always works.
    return _regex_strip(raw_html)


def extract_title(raw_html: str, fallback: str = "") -> str:
    m = re.search(r"(?is)<title>(.*?)</title>", raw_html)
    return _regex_strip(m.group(1)) if m else fallback


# --------------------------------------------------------------------------- #
# Search backends
# --------------------------------------------------------------------------- #

class SearchBackend:
    name = "base"

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Return [{url, title, score, snippet}]."""
        raise NotImplementedError


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "is",
    "are", "was", "were", "be", "with", "as", "by", "at", "from", "that", "this",
    "it", "its", "they", "has", "have", "had", "will", "can", "into", "than",
    "then", "so", "such", "we", "you", "not", "no", "what", "how", "do", "does",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _STOPWORDS and len(w) > 2}


class LocalCorpusBackend(SearchBackend):
    """Offline backend: rank local fixture files by keyword overlap. CI-safe."""

    name = "local"

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent.parent

    def _files(self) -> list[Path]:
        exts = {".txt", ".md", ".html", ".htm"}
        if os.environ.get("GROUNDWORK_CORPUS"):
            roots = [Path(os.environ["GROUNDWORK_CORPUS"])]
        else:
            roots = [self.root / "corpus", self.root / "redteam"]
        files: list[Path] = []
        for base in roots:
            if base.exists():
                files.extend(p for p in base.rglob("*") if p.suffix.lower() in exts and p.is_file())
        return files

    def search(self, query: str, k: int = 5) -> list[dict]:
        q = _tokens(query)
        scored = []
        for path in self._files():
            try:
                text = extract_main_text(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            overlap = len(q & _tokens(text))
            if overlap:
                scored.append((overlap, path, text))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [{"url": p.as_uri(), "title": p.stem.replace("_", " ").title(),
                 "score": float(s), "snippet": t[:160]} for s, p, t in scored[:k]]


class TavilyBackend(SearchBackend):
    """Real web search via the Tavily API (https://tavily.com)."""

    name = "tavily"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")

    @retry(attempts=3, exceptions=(Exception,))
    def search(self, query: str, k: int = 5) -> list[dict]:
        import json  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY not set")
        payload = json.dumps({
            "api_key": self.api_key, "query": query,
            "max_results": k, "search_depth": "advanced",
        }).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        results = []
        for r in data.get("results", []):
            results.append({
                "url": r.get("url", ""), "title": r.get("title", ""),
                "score": float(r.get("score", 0.0)), "snippet": (r.get("content") or "")[:160],
            })
        return results


def get_search_backend() -> SearchBackend:
    choice = os.environ.get("GROUNDWORK_SEARCH_BACKEND", "").lower()
    if choice == "tavily" or (not choice and os.environ.get("TAVILY_API_KEY")):
        log.info("search backend: tavily (live web)")
        return TavilyBackend()
    log.info("search backend: local corpus (offline)")
    return LocalCorpusBackend()
