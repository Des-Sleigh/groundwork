"""Layer 3: the orchestrator (capstone).

planner (Sonnet-class) decomposes the question into sub-tasks
  -> workers (Haiku-class, in parallel) each research a sub-task via the
     Layer-2 research agent
  -> critic (Sonnet-class) reviews each worker's brief, running the grounding +
     injection checks, and sends a failing brief back for one revision
  -> synthesize the accepted briefs into a final, cited answer.

Cost is accounted by role so the tiered-routing decision (cheap workers,
stronger planner/critic) is visible at the end of the run.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from core.cost import CostAccounting
from core.providers import MockProvider, TieredRouter
from core.tracing import Tracer
from research_agent import grounding
from research_agent.agent import ResearchAgent

# A worker brief is accepted only if at least this share of its claims grounded.
GROUNDING_ACCEPT_RATIO = 0.5


class Orchestrator:
    def __init__(self, router: TieredRouter | None = None, max_workers: int = 4,
                 tracer: Tracer | None = None):
        self.router = router or TieredRouter()
        self.tracer = tracer or Tracer()
        self.cost = CostAccounting()
        self.max_workers = max_workers

    # -- planner --------------------------------------------------------------
    def plan(self, question: str) -> list[str]:
        self.tracer.thought("decomposing question", question, role="planner")
        provider = self.router.for_role("planner")
        system = ("You are a research lead. Split the question into 2-4 independent sub-tasks "
                  "that can be researched in parallel. Output one sub-task per line, no numbering.")
        gen = provider.generate(f"Question: {question}", system=system, max_tokens=256)
        self.cost.add("planner", gen.model, gen.input_tokens, gen.output_tokens)
        tasks = [ln.strip("-• \t") for ln in gen.text.splitlines() if ln.strip()]
        tasks = tasks[:4] or [question]
        self.tracer.decision("sub-tasks", tasks, role="planner")
        return tasks

    def _grounding_provider(self):
        """A real model for final-answer grounding; None (skip) when mock."""
        provider = self.router.for_role("critic")
        return None if isinstance(provider, MockProvider) else provider

    # -- one worker -----------------------------------------------------------
    def _run_worker(self, task: str):
        agent = ResearchAgent(router=self.router, tracer=self.tracer, cost=self.cost, role="worker")
        result = agent.run(task)
        result["task"] = task
        return result, agent  # agent carries the gathered sources for final grounding

    # -- critic ---------------------------------------------------------------
    def critique(self, result: dict) -> dict:
        g = result["grounding"]
        ratio = (g["verified"] / g["total"]) if g["total"] else 0.0
        injected = bool(result["injection_flags"])
        accepted = ratio >= GROUNDING_ACCEPT_RATIO
        reason = (f"grounded {g['verified']}/{g['total']} "
                  f"({ratio:.0%}); injection_flags={len(result['injection_flags'])}")
        # Note: injection is flagged but does not by itself fail the brief — the
        # agent already refused to obey it; we record that it was caught.
        verdict = {"accepted": accepted, "ratio": ratio, "reason": reason, "injected": injected}
        self.tracer.decision("critic verdict", {"task": result["task"], **verdict}, role="critic")
        return verdict

    # -- run ------------------------------------------------------------------
    def run(self, question: str) -> dict:
        tasks = self.plan(question)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            pairs = list(pool.map(self._run_worker, tasks))

        accepted, accepted_agents, revised_count, rejected = [], [], 0, []
        for result, agent in pairs:
            verdict = self.critique(result)
            if verdict["accepted"]:
                accepted.append(result)
                accepted_agents.append(agent)
                continue
            # One revision pass for a rejected brief.
            self.tracer.decision("revising rejected brief", result["task"], role="critic")
            revised_count += 1
            revised, ragent = self._run_worker(result["task"])
            rev_verdict = self.critique(revised)
            if rev_verdict["accepted"]:
                accepted.append(revised)
                accepted_agents.append(ragent)
            else:
                rejected.append(revised["task"])

        final = self.synthesize(question, accepted)

        # Final-answer grounding: re-verify the synthesized brief against the
        # union of the accepted workers' sources, so the brief carries its own
        # "X of Y verified" footer (skipped in mock mode).
        final_grounding = None
        gp = self._grounding_provider()
        if gp and accepted_agents:
            srcs = {}
            for ag in accepted_agents:
                for s in ag.sources:
                    srcs[s.url] = s
            if srcs:
                report = grounding.verify_answer(final, list(srcs.values()), provider=gp)
                final = grounding.annotate_flagged(final, report)
                final_grounding = report.to_dict()
                self.tracer.decision("final grounding", report.summary(), role="critic")

        return {
            "question": question,
            "answer": final,
            "final_grounding": final_grounding,
            "n_tasks": len(tasks),
            "n_accepted": len(accepted),
            "n_revised": revised_count,
            "rejected_tasks": rejected,
            "cost": self.cost.breakdown(),
            "cost_render": self.cost.render(),
            "trace": self.tracer.to_list(),
            "worker_results": [r for r, _ in pairs],
        }

    # -- final synthesis ------------------------------------------------------
    def synthesize(self, question: str, accepted: list[dict]) -> str:
        if not accepted:
            return "No worker brief passed the grounding bar; nothing could be reliably synthesized."
        provider = self.router.for_role("critic")
        briefs = "\n\n".join(f"## {r['task']}\n{r['answer']}" for r in accepted)
        system = ("You are the research lead writing the final brief. Combine the verified "
                  "sub-task findings into one coherent, cited answer. Keep only well-supported claims.")
        gen = provider.generate(f"Question: {question}\n\nVerified findings:\n{briefs}",
                                system=system, max_tokens=1024)
        self.cost.add("critic", gen.model, gen.input_tokens, gen.output_tokens)
        self.tracer.result("final synthesis complete", role="critic")
        return gen.text
