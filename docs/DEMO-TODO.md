# Demo assets TODO (for Des)

The README references two images that you should capture (the live demo is a
recorded walkthrough by your choice, so these are the showcase assets):

- `docs/dashboard.png` — a screenshot of the trace dashboard mid-run (the live
  trajectory timeline on the left, grounding meter + cost bars on the right).
- `docs/demo.gif` (optional but high-impact) — a short screen recording of a
  real query: type a question → watch the plan → tool calls → grounding → critic
  stream, then the cited answer appear.

How to capture (real models, best look):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=tvly-...            # optional, for live web
uvicorn api.server:app --port 8000        # backend (real mode)
cd web && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# open http://localhost:3000, run the example question, screenshot / record
```

Save the files at the paths above and commit. Until then the README image links
will show as broken on GitHub.
