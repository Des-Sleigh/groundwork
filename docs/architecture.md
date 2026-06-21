# Groundwork architecture

Three layers over a shared core, built **MCP → agent → orchestrator**. Each
layer stands alone as a working demo, so partial completion still yields
pinnable, runnable work.

```
                ┌──────────────────────────────────────────────────────┐
                │  core/  (shared, depends on nothing else)            │
                │  providers.py  tracing.py  cost.py  types.py         │
                └──────────────────────────────────────────────────────┘
                          ▲              ▲              ▲
                          │              │              │
   ┌──────────────────────┴───┐  ┌───────┴────────────┐  ┌──┴───────────────────────┐
   │ LAYER 1  mcp_server/     │  │ LAYER 2 research_  │  │ LAYER 3  orchestrator/    │
   │ server.py  tools.py      │  │ agent/             │  │ loop.py                   │
   │                          │  │ agent.py           │  │                           │
   │ web_search  fetch_url    │  │ grounding.py       │  │ planner ─┐                │
   │ extract_claims           │◄─┤ defenses.py        │◄─┤   (sonnet)│ decompose     │
   │ check_grounding          │  │                    │  │ workers ◄─┘ (haiku, parallel)
   │                          │  │ plan→gather→       │  │   each runs a Layer-2 agent│
   │ spec-compliant MCP       │  │ synthesize→ground  │  │ critic  ── grounding +     │
   │ (Claude Desktop, etc.)   │  │ w/ inline citations│  │   (sonnet) injection checks│
   └──────────────────────────┘  └────────────────────┘  │          → retry → synth   │
                                                          └────────────────────────────┘
```

## Layer 1 — MCP server (build first; independently demoable)

A spec-compliant MCP server on the official MCP Python SDK exposing four tools:

| Tool | Purpose |
|---|---|
| `web_search(query)` | ranked results |
| `fetch_url(url)` | cleaned page text + provenance; content tagged **untrusted** |
| `extract_claims(text)` | list of atomic claims |
| `check_grounding(claim, sources)` | supported / unsupported + which source |

The tool *logic* lives in `mcp_server/tools.py` as plain functions, so the same
implementations back both the MCP server and the in-process agent. Connect the
server to any MCP client (e.g. Claude Desktop) to give it grounded web research
— config snippet in `mcp_server/server.py`.

**Standalone demo:** `python -m mcp_server.server`.

## Layer 2 — Grounded research agent (consumes Layer 1)

`agent.py` takes an AI-for-business question, plans sub-questions, gathers
sources via the Layer-1 tools, and synthesizes an answer with inline citations.

- **Grounding** (`grounding.py`) — after synthesis, every claim is verified
  against the retrieved sources; the output carries a grounding report
  ("X of Y claims verified") and ungrounded claims are flagged, not shipped
  silently.
- **Injection defense** (`defenses.py`) — fetched content is wrapped as data and
  scanned for instruction-like patterns. An injection attempt is flagged and
  ignored, never obeyed. The red-team suite (`tests/test_defenses.py`) asserts
  both properties against the benign canary pages in `redteam/injection_pages/`.
- **Production hygiene** — tool-error recovery in `gather`, a full trajectory
  trace (`core/tracing.py`), and per-run cost (`core/cost.py`).

## Layer 3 — Orchestrator (capstone; wraps Layer 2)

`loop.py`: a **planner** (Sonnet-class) decomposes the question → **workers**
(Haiku-class, in parallel) each research a sub-task via the Layer-2 agent → a
**critic** (Sonnet-class) reviews each brief, running the grounding + injection
checks and sending a failing brief back for one revision → final synthesis.

The run reports a **cost breakdown by role**, making the tiered-routing decision
(cheap workers, stronger planner/critic) visible.

## The four differentiators, threaded through every layer

1. **Grounding verification** — every claim traces to a retrieved source;
   ungrounded claims are flagged (ICD-203-style sourcing discipline as code).
2. **Prompt-injection resistance** — fetched content is untrusted data, with
   structural + detection defenses and a benign red-team suite proving it holds.
3. **Cost-aware tiered routing** — Haiku-class workers, Sonnet-class
   planner/critic, via `core/providers.TieredRouter`.
4. **Observability** — full step/trajectory tracing + per-run token/cost
   accounting.
