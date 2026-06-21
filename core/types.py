"""Shared data types for Groundwork.

These flow across all three layers (MCP server, research agent, orchestrator),
so they live in core/ and depend on nothing else in the project.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Source:
    """A retrieved source. Content fetched from the web is *untrusted data*."""

    url: str
    title: str
    text: str
    fetched_at: float = field(default_factory=time.time)
    untrusted: bool = True  # fetched content is data, never instructions

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8", "replace")).hexdigest()[:16]

    def provenance(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "fetched_at": self.fetched_at,
            "content_hash": self.content_hash,
            "untrusted": self.untrusted,
        }


@dataclass
class Claim:
    """An atomic factual assertion extracted from synthesized text."""

    text: str
    id: Optional[str] = None


@dataclass
class Citation:
    """Links a claim to the source span that supports it."""

    claim: str
    source_url: str
    supported: bool
    evidence: str = ""
    score: float = 0.0  # support strength, 0-1


@dataclass
class GroundingResult:
    """The outcome of verifying one claim against the available sources."""

    claim: str
    supported: bool
    best_source_url: Optional[str]
    evidence: str
    score: float


@dataclass
class GroundingReport:
    """Aggregate grounding verdict for a synthesized answer."""

    results: list[GroundingResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def verified(self) -> int:
        return sum(1 for r in self.results if r.supported)

    @property
    def flagged(self) -> list[GroundingResult]:
        return [r for r in self.results if not r.supported]

    def summary(self) -> str:
        return f"{self.verified} of {self.total} claims verified against sources"

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "verified": self.verified,
            "total": self.total,
            "results": [asdict(r) for r in self.results],
        }


@dataclass
class TraceStep:
    """One step in an agent's trajectory, for observability."""

    kind: str  # thought | tool_call | result | decision | error
    label: str
    detail: Any = None
    at: float = field(default_factory=time.time)
    role: str = "agent"  # planner | worker | critic | agent

    def to_dict(self) -> dict:
        return asdict(self)
