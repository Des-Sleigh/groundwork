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
    """Thread-safe append-only log of TraceSteps (workers run in parallel).

    `sink`, if given, is called with each step's dict as it's recorded — used by
    the API to stream the trajectory live over SSE.
    """

    def __init__(self, echo: bool = False, sink=None):
        self._steps: list[TraceStep] = []
        self._lock = threading.Lock()
        self.echo = echo
        self.sink = sink

    def record(self, kind: str, label: str, detail=None, role: str = "agent") -> TraceStep:
        step = TraceStep(kind=kind, label=label, detail=detail, role=role)
        with self._lock:
            self._steps.append(step)
        if self.echo:
            print(f"[{role}/{kind}] {label}")
        if self.sink:
            try:
                self.sink(step.to_dict())
            except Exception:  # noqa: BLE001 — never let a sink error break a run
                pass
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
