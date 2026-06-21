# Generating the committed sample research report

`reports/sample_research_report.md` is meant to hold a **real, grounded, cited
AI-for-business brief** produced by a live run. It hasn't been generated yet
because that needs an Anthropic API key (and, ideally, a live web-search/fetch
backend) — and Groundwork never fabricates results.

## Quick offline demo (no key)

Proves the full planner → workers → critic → synthesize loop, grounding report,
injection flags, and per-role cost breakdown, using mock models over the fixture
corpus:

```bash
python run_demo.py
```

## Real run (needs a key)

1. `export ANTHROPIC_API_KEY=sk-ant-...` (or use `.env`).
2. Use the default `TieredRouter` (routes to Anthropic) instead of the mock
   router in `run_demo.py`, or call the orchestrator directly:

   ```python
   from orchestrator.loop import Orchestrator
   orch = Orchestrator()  # default tiers: planner/critic=sonnet, workers=haiku
   result = orch.run(
       "How are mid-market logistics firms using AI for demand forecasting, "
       "and what ROI evidence exists?"
   )
   open("reports/sample_research_report.md", "w").write(result["answer"])
   ```

3. For genuinely live sourcing, wire a real search/HTTP backend into
   `mcp_server/tools.web_search` / `fetch_url` (the offline default reads the
   `corpus/` fixtures). Then commit the generated brief:

   ```bash
   git add reports/sample_research_report.md && git commit -m "Add sample research brief"
   ```
