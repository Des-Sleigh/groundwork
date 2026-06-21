"""Orchestrator: the critic rejects an ungrounded brief and triggers a revision,
and cost is accounted by role.

Offline, deterministic: a stateful mock makes the first synthesis ungrounded
(fabricated claim) and the revision grounded (echoes real source text), so the
planner -> worker -> critic -> retry path is exercised end-to-end.
"""

import re
import threading

from core.providers import MockProvider, TieredRouter
from orchestrator.loop import Orchestrator


class StatefulResponder:
    def __init__(self):
        self.synth_calls = 0
        self.lock = threading.Lock()

    def __call__(self, prompt, system):
        sys = system or ""
        if "sub-task" in sys:                       # planner: one task -> one worker
            return "AI demand forecasting in logistics"
        if "break a research question" in sys:       # worker.plan
            return "AI demand forecasting adoption"
        if "research lead writing the final" in sys: # final synthesis
            bodies = re.findall(r"<source[^>]*>(.*?)</source>", prompt, re.DOTALL)
            return " ".join(b.strip()[:120] for b in bodies[:2]) or "Final brief."
        if "grounded research analyst" in sys:       # worker synthesis
            with self.lock:
                self.synth_calls += 1
                n = self.synth_calls
            if n == 1:
                # Ungrounded: a fabricated claim with no support in the sources.
                return "Telepathic dolphins operate every distribution center on the moon."
            # Grounded: a clean declarative claim that overlaps the fixture corpus.
            return ("Mid-market logistics firms apply machine learning demand forecasting "
                    "to reduce safety stock and improve utilization.")
        return "fallback"


def test_critic_rejects_then_revises_and_cost_is_by_role():
    responder = StatefulResponder()
    router = TieredRouter(provider_factory=lambda m: MockProvider(m, responder=responder))
    orch = Orchestrator(router=router, max_workers=2)
    result = orch.run("How is AI used for demand forecasting in logistics?")

    # The first brief was ungrounded -> at least one revision happened.
    assert result["n_revised"] >= 1
    assert result["n_accepted"] >= 1

    # Cost is broken down by role, including the tiered roles.
    by_role = result["cost"]["by_role"]
    assert "planner" in by_role
    assert "worker" in by_role
    assert "critic" in by_role

    # A trace was captured across roles.
    roles_seen = {step["role"] for step in result["trace"]}
    assert {"planner", "worker", "critic"} <= roles_seen
