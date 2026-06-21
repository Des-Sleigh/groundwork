"""Token + dollar accounting, per step and per run, broken down by role.

Makes the tiered-routing decision (cheap workers, stronger planner/critic)
visible: at the end of a run you can see exactly where the spend went.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# USD per 1M tokens (input, output). Keep in sync with Anthropic pricing.
PRICING = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


@dataclass
class _Bucket:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


@dataclass
class CostAccounting:
    """Accumulates usage across a run, keyed by role and by model."""

    by_role: dict = field(default_factory=dict)
    by_model: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, role: str, model: str, input_tokens: int, output_tokens: int) -> float:
        c = price(model, input_tokens, output_tokens)
        with self._lock:  # workers accumulate cost in parallel
            for key, store in ((role, self.by_role), (model, self.by_model)):
                b = store.setdefault(key, _Bucket())
                b.input_tokens += input_tokens
                b.output_tokens += output_tokens
                b.cost_usd += c
                b.calls += 1
        return c

    @property
    def total_usd(self) -> float:
        return sum(b.cost_usd for b in self.by_role.values())

    @property
    def total_tokens(self) -> int:
        return sum(b.input_tokens + b.output_tokens for b in self.by_role.values())

    def breakdown(self) -> dict:
        return {
            "total_usd": round(self.total_usd, 6),
            "total_tokens": self.total_tokens,
            "by_role": {
                k: {"calls": b.calls, "input_tokens": b.input_tokens,
                    "output_tokens": b.output_tokens, "cost_usd": round(b.cost_usd, 6)}
                for k, b in self.by_role.items()
            },
            "by_model": {
                k: {"calls": b.calls, "input_tokens": b.input_tokens,
                    "output_tokens": b.output_tokens, "cost_usd": round(b.cost_usd, 6)}
                for k, b in self.by_model.items()
            },
        }

    def render(self) -> str:
        lines = [f"Total: ${self.total_usd:.4f} over {self.total_tokens} tokens"]
        lines.append("By role:")
        for role, b in sorted(self.by_role.items()):
            lines.append(f"  {role:<9} {b.calls:>2} calls  ${b.cost_usd:.4f}  "
                         f"({b.input_tokens} in / {b.output_tokens} out)")
        return "\n".join(lines)
