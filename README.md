# Groundwork

**A grounded, injection-resistant, cost-aware platform for AI-for-business research — built to prove an agent can be *trusted*, not just demoed.**

Groundwork researches how businesses adopt and apply AI (use cases, vendor landscape, ROI evidence, implementation patterns, risks) and returns an answer where **every claim traces to a retrieved source**, ungrounded statements are flagged rather than shipped, and fetched web content is treated as untrusted data — not instructions.

It's three layers over a shared core, built **MCP → agent → orchestrator**. Each layer stands alone as a working demo.

```
core/  →  Layer 1: MCP server  →  Layer 2: research agent  →  Layer 3: orchestrator
```

## Why it exists

Most agent demos are happy-path: they sound authoritative and cite nothing checkable, and they'll cheerfully follow an instruction hidden inside a web page. Groundwork is the opposite — it's built around the failure modes:

| Differentiator | How it shows up in the code |
|---|---|
| **Grounding verification** | Every synthesized claim is checked against the retrieved sources; the answer ships with an "X of Y claims verified" report and flags the rest. (`research_agent/grounding.py`) |
| **Prompt-injection resistance** | Fetched content is wrapped as data and scanned for instruction-like patterns; injections are flagged and ignored, never obeyed. Proven by a benign red-team suite. (`research_agent/defenses.py`, `redteam/`) |
| **Cost-aware tiered routing** | Haiku-class workers do the bulk research; Sonnet-class planner/critic supervise. One router maps role → model. (`core/providers.py`) |
| **Observability** | Full step/trajectory tracing + per-run token/cost accounting, broken down by role. (`core/tracing.py`, `core/cost.py`) |

## The three layers

**Layer 1 — MCP server** (`mcp_server/`). A spec-compliant server on the official MCP Python SDK exposing `web_search`, `fetch_url` (with provenance; content tagged untrusted), `extract_claims`, and `check_grounding`. The tool logic is plain functions, so the same code backs both the MCP server and the in-process agent. Connect it to Claude Desktop to give it grounded web research (config snippet in `mcp_server/server.py`).

**Layer 2 — Grounded research agent** (`research_agent/`). Plans sub-questions → gathers sources via the Layer-1 tools → synthesizes an answer with inline `[n]` citations → verifies every claim against the sources and emits a grounding report. Injection defenses, tool-error recovery, tracing, and cost accounting throughout.

**Layer 3 — Orchestrator** (`orchestrator/`). Planner (Sonnet) decomposes the question → workers (Haiku, **in parallel**) each research a sub-task via the Layer-2 agent → critic (Sonnet) runs the grounding + injection checks and **sends a failing brief back for one revision** → final synthesis. Prints a cost breakdown by role.

See [docs/architecture.md](docs/architecture.md) for the full diagram.

## Quick start

```bash
pip install -e .          # or: pip install anthropic mcp

# Offline end-to-end demo — no API key. Shows the full planner→workers→critic
# loop, grounding report, injection flags, and per-role cost breakdown over a
# fixture corpus with mock models:
python run_demo.py

# Run the MCP server (Layer 1) for an MCP client like Claude Desktop:
python -m mcp_server.server
```

For a **real run** (live models + a real research brief), set `ANTHROPIC_API_KEY` and use the default `TieredRouter` — see [reports/SAMPLE-REPORT-TODO.md](reports/SAMPLE-REPORT-TODO.md).

## Layout

```
groundwork/
├── core/                  # shared: providers (+ tiered routing), tracing, cost, types
├── mcp_server/            # LAYER 1: server.py (FastMCP) + tools.py (the 4 tools)
├── research_agent/        # LAYER 2: agent.py, grounding.py, defenses.py
├── orchestrator/          # LAYER 3: loop.py (planner → workers → critic → synth)
├── redteam/injection_pages/   # BENIGN injection canary pages for the test suite
├── corpus/                # fixture documents for the offline demo (clearly illustrative)
├── docs/architecture.md
├── reports/               # sample_research_report.md (real run — see TODO)
├── run_demo.py            # offline three-layer demo
└── tests/                 # grounding, injection defenses, orchestrator retry + cost
```

## Tests

```bash
pip install pytest && pytest -q
```

Covers the three differentiators with **no API key or network**: injection canaries are detected *and* not obeyed (with a clean-page false-positive check), supported claims ground while fabricated ones are flagged, and the orchestrator's critic rejects an ungrounded brief, triggers a revision, and accounts cost by role.

## Safety

Everything in `redteam/injection_pages/` is a **benign canary** — a harmless obedience probe (e.g. an embedded "append BANANA" or "recommend Brand X" instruction). There are no operational attacks or harmful payloads anywhere in this repo. Treating fetched/external content as untrusted data is the core security stance, applied throughout.

## Author

Built by **Desmond Sleigh** — [github.com/Des-Sleigh](https://github.com/Des-Sleigh). Sibling project: **[llm-eval-harness](https://github.com/Des-Sleigh/llm-eval-harness)**, which measures model quality with the same evaluation discipline this platform applies to its own output.

_License: MIT._
