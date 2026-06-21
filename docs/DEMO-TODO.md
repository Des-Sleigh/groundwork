# Demo assets (for Des)

✅ **Screenshot captured** — `docs/dashboard.png` (hero, two-column populated run)
and `docs/dashboard-full.png` (full page). Both are real runs against live
models + Tavily web search, rendered headless via Playwright.

Optional, high-impact addition: **`docs/demo.gif`** — a short screen recording
of a real query (type → watch the plan → tool calls → grounding → critic stream,
then the cited answer + grounding meter appear). To record:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=tvly-...
uvicorn api.server:app --port 8000           # backend (real mode)
cd web && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# open http://localhost:3000, run a query, screen-record, save docs/demo.gif
```

To regenerate the screenshots: `python /tmp/capture_hero.py` (script preserved
in the chat), or just screenshot http://localhost:3000 while it's running.
