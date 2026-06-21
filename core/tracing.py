"""Structured trajectory tracing.

Every meaningful step (thought / tool_call / result / decision / error) is
recorded as a TraceStep so a run is fully auditable after the fact — the
observability differentiator.
"""

from __future__ import annotations

import json
import threading

from .types import TraceStep


class Tracer:
    """Thread-safe append-only log of TraceSteps (workers run in parallel)."""

    def __init__(self, echo: bool = False):
        self._steps: list[TraceStep] = []
        self._lock = threading.Lock()
        self.echo = echo

    def record(self, kind: str, label: str, detail=None, role: str = "agent") -> TraceStep:
        step = TraceStep(kind=kind, label=label, detail=detail, role=role)
        with self._lock:
            self._steps.append(step)
        if self.echo:
            print(f"[{role}/{kind}] {label}")
        return step

    # Convenience wrappers.
    def thought(self, label, detail=None, role="agent"):
        return self.record("thought", label, detail, role)

    def tool_call(self, label, detail=None, role="agent"):
        return self.record("tool_call", label, detail, role)

    def result(self, label, detail=None, role="agent"):
        return self.record("result", label, detail, role)

    def decision(self, label, detail=None, role="agent"):
        return self.record("decision", label, detail, role)

    def error(self, label, detail=None, role="agent"):
        return self.record("error", label, detail, role)

    @property
    def steps(self) -> list[TraceStep]:
        return list(self._steps)

    def to_list(self) -> list[dict]:
        return [s.to_dict() for s in self._steps]

    def dumps(self) -> str:
        return json.dumps(self.to_list(), indent=2, default=str)
