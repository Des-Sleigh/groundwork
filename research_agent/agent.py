"""Layer 2: the grounded research agent.

Pipeline: plan sub-questions -> gather sources (via the Layer-1 tools) ->
synthesize an answer with inline citations -> verify every claim against the
sources. Fetched content is handled as untrusted data throughout (defenses.py),
the full trajectory is traced (core.tracing), and per-run cost is accounted by
role (core.cost).

Runs offline with mock providers (tests/dry run) and against the Anthropic API
when a key is present — the model calls go through the TieredRouter either way.
"""

from __future__ import annotations

from core.cost import CostAccounting
from core.providers import TieredRouter
from core.tracing import Tracer
from core.types import Source
from mcp_server import tools

from . import defenses, grounding


class ResearchAgent:
    def __init__(self, router: TieredRouter | None = None, tracer: Tracer | None = None,
                 cost: CostAccounting | None = None, max_sources: int = 5, role: str = "agent"):
        self.router = router or TieredRouter()
        self.tracer = tracer or Tracer()
        self.cost = cost or CostAccounting()
        self.max_sources = max_sources
        self.role = role

    # -- model call helper: routes by role, records cost + a trace step --------
    def _ask(self, role: str, prompt: str, system: str | None = None, max_tokens: int = 1024) -> str:
        provider = self.router.for_role(role)
        gen = provider.generate(prompt, system=system, max_tokens=max_tokens)
        self.cost.add(role, gen.model, gen.input_tokens, gen.output_tokens)
        return gen.text

    def _grounding_provider(self):
        """Use a real model for entailment grounding; None (lexical) when mock."""
        from core.providers import MockProvider  # noqa: PLC0415

        provider = self.router.for_role("critic")
        return None if isinstance(provider, MockProvider) else provider

    # -- plan -----------------------------------------------------------------
    def plan(self, question: str) -> list[str]:
        self.tracer.thought("planning sub-questions", question, role=self.role)
        system = "You break a research question into 3-5 focused sub-questions. Output one per line, no numbering."
        text = self._ask(self.role, f"Research question: {question}", system=system, max_tokens=256)
        subqs = [ln.strip("-• \t") for ln in text.splitlines() if ln.strip()]
        if not subqs:
            subqs = [question]
        self.tracer.decision("sub-questions", subqs, role=self.role)
        return subqs[:5]

    # -- gather ---------------------------------------------------------------
    def gather(self, subquestions: list[str]) -> tuple[list[Source], list[dict]]:
        sources: dict[str, Source] = {}
        flags: list[dict] = []
        for sq in subquestions:
            self.tracer.tool_call("web_search", sq, role=self.role)
            try:
                hits = tools.web_search(sq, k=3)
            except Exception as e:  # tool-error recovery
                self.tracer.error("web_search failed", str(e), role=self.role)
                continue
            for hit in hits:
                url = hit["url"]
                if url in sources:
                    continue
                self.tracer.tool_call("fetch_url", url, role=self.role)
                try:
                    src = tools.fetch_url(url)
                except Exception as e:
                    self.tracer.error("fetch_url failed", f"{url}: {e}", role=self.role)
                    continue
                # Injection defense: scan untrusted content, flag (don't obey).
                scan = defenses.scan_for_injection(src.text)
                if scan.suspicious:
                    flags.append({"url": url, "matches": scan.matches})
                    self.tracer.decision("injection flagged", {"url": url, "matches": scan.matches}, role=self.role)
                sources[url] = src
                self.tracer.result("fetched", src.provenance(), role=self.role)
                if len(sources) >= self.max_sources:
                    break
            if len(sources) >= self.max_sources:
                break
        return list(sources.values()), flags

    # -- synthesize -----------------------------------------------------------
    def synthesize(self, question: str, sources: list[Source]) -> str:
        numbered = []
        for i, src in enumerate(sources, 1):
            numbered.append(f"[{i}] " + defenses.wrap_untrusted(src.title, src.url, src.text[:2000]))
        body = "\n\n".join(numbered)
        system = (
            "You are a grounded research analyst. Answer the question using ONLY the "
            "numbered sources. Cite every factual claim inline with [n]. If the sources "
            "don't support a point, say so rather than guessing. " + defenses.UNTRUSTED_SYSTEM_NOTE
        )
        prompt = f"Question: {question}\n\nSources:\n{body}\n\nWrite a concise, cited brief."
        self.tracer.thought("synthesizing answer", {"n_sources": len(sources)}, role=self.role)
        return self._ask(self.role, prompt, system=system, max_tokens=1024)

    # -- run ------------------------------------------------------------------
    def run(self, question: str) -> dict:
        self.tracer.thought("run start", question, role=self.role)
        subqs = self.plan(question)
        sources, injection_flags = self.gather(subqs)

        if not sources:
            self.tracer.error("no sources gathered", question, role=self.role)
            return {
                "question": question, "answer": "No sources could be retrieved.",
                "grounding": {"summary": "0 of 0 claims verified", "verified": 0, "total": 0, "results": []},
                "injection_flags": injection_flags, "sources": [],
                "trace": self.tracer.to_list(), "cost": self.cost.breakdown(),
            }

        answer = self.synthesize(question, sources)
        report = grounding.verify_answer(answer, sources, provider=self._grounding_provider())
        self.tracer.decision("grounding", report.summary(), role=self.role)
        annotated = grounding.annotate_flagged(answer, report)

        return {
            "question": question,
            "answer": annotated,
            "grounding": report.to_dict(),
            "injection_flags": injection_flags,
            "sources": [s.provenance() for s in sources],
            "trace": self.tracer.to_list(),
            "cost": self.cost.breakdown(),
        }
