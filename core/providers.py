"""Model providers + tiered routing.

Anthropic today; the `Provider` interface keeps a local backend (e.g. MLX) a
drop-in away. `TieredRouter` maps a *role* to a *model* so the cost-aware
routing decision (Haiku-class workers, Sonnet-class planner/critic) lives in
one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Generation:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class Provider:
    name: str

    def generate(self, prompt: str, system: str | None = None, max_tokens: int = 1024) -> Generation:
        raise NotImplementedError


class AnthropicProvider(Provider):
    """Anthropic Messages API. SDK imported lazily so offline code/tests run."""

    def __init__(self, model: str):
        self.name = model
        self.model = model
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            import anthropic  # noqa: PLC0415

            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, prompt: str, system: str | None = None, max_tokens: int = 1024) -> Generation:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = self._client_lazy().messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        return Generation(text, resp.usage.input_tokens, resp.usage.output_tokens, self.model)


class MockProvider(Provider):
    """Offline deterministic provider for tests/dry runs. Not for real reports."""

    def __init__(self, model: str = "mock", responder=None):
        self.name = model
        self.model = model
        # responder: callable(prompt, system) -> str
        self.responder = responder or (lambda prompt, system: "")

    def generate(self, prompt: str, system: str | None = None, max_tokens: int = 1024) -> Generation:
        text = self.responder(prompt, system)
        return Generation(text, len(prompt) // 4, len(text) // 4, self.model)


# Default role -> model tiers. Cheap models do the bulk work; stronger models
# plan and critique.
DEFAULT_TIERS = {
    "planner": "claude-sonnet-4-6",
    "worker": "claude-haiku-4-5",
    "critic": "claude-sonnet-4-6",
    "agent": "claude-haiku-4-5",
    "judge": "claude-sonnet-4-6",
}


class TieredRouter:
    """Resolves a role to a provider, caching one provider per model."""

    def __init__(self, tiers: dict | None = None, provider_factory=None):
        self.tiers = dict(DEFAULT_TIERS)
        if tiers:
            self.tiers.update(tiers)
        self._factory = provider_factory or self._default_factory
        self._cache: dict[str, Provider] = {}

    @staticmethod
    def _default_factory(model: str) -> Provider:
        if model.startswith("mock"):
            return MockProvider(model)
        return AnthropicProvider(model)

    def model_for(self, role: str) -> str:
        return self.tiers.get(role, self.tiers["agent"])

    def for_role(self, role: str) -> Provider:
        model = self.model_for(role)
        if model not in self._cache:
            self._cache[model] = self._factory(model)
        return self._cache[model]
