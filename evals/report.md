# Groundwork evaluation report

Measures Groundwork's grounding accuracy and injection-detection on labeled datasets. The lexical grounder and the regex injection detector need no API key, so these numbers are reproducible in CI.

## Grounding accuracy (claim supported by sources?)

| Method | n | Precision | Recall | F1 | Accuracy |
|---|---:|---:|---:|---:|---:|
| lexical heuristic | 30 | 0.86 | 1.00 | 0.92 | 0.90 |
| LLM entailment | — | — | — | — | _set ANTHROPIC_API_KEY to measure_ |

## Injection detection (manipulation attempt flagged?)

| Method | n | Precision | Recall | F1 | Accuracy |
|---|---:|---:|---:|---:|---:|
| regex pattern scan | 20 | 1.00 | 1.00 | 1.00 | 1.00 |

> Datasets: `evals/datasets/`. Re-run with `python -m evals.run`.
