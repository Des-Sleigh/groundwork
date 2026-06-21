# Benchmark: naive RAG vs. grounded (Groundwork)

Same labeled claim set (`evals/datasets/grounding.jsonl`); the question is how many *unsupported* claims each approach ships as if true.

| Approach | Hallucinations shipped ↓ | Valid claims kept ↑ |
|---|---:|---:|
| Naive RAG (no grounding) | 100% (12/12) | 100% (18/18) |
| Groundwork — lexical grounder | 25% (3/12) | 100% (18/18) |
| Groundwork — LLM entailment (claude-sonnet-4-6) † | **0%** (0/12) | 94% (17/18) |

**Naive RAG ships 100% of hallucinations** — it has no notion of whether a claim is supported. Groundwork's grounding filter is the difference between a confident-but-wrong answer and a trustworthy one. The lexical grounder already removes most; the LLM entailment grounder removes essentially all, at a small cost in valid-claim retention.

† LLM-entailment row from the measured eval on this same set (`evals/report.md`: precision 1.00, recall 0.94). Run `benchmark.run` with a key to compute it live here.

> Reproduce: `python -m benchmark.run` (LLM row needs a key).
