"""FastAPI backend for the Groundwork trace dashboard.

POST /research streams the agent's trajectory live over Server-Sent Events:
each trace step (plan, tool call, grounding decision, ...) is emitted as it
happens, followed by the final result (answer, grounding report, injection
flags, cost breakdown).

Runs in two modes:
  - real:  ANTHROPIC_API_KEY set -> live models (+ Tavily if TAVILY_API_KEY)
  - mock:  no key, or GROUNDWORK_MOCK=1 -> offline deterministic demo

    uvicorn api.server:app --reload
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
from typing import Optional

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import store
from core.providers import MockProvider, TieredRouter
from core.tracing import Tracer
from orchestrator.loop import Orchestrator

# Persist runs + cache fetches in one DB. Export the path so tools.fetch_url
# (in worker threads) uses the same cache.
DB = store.default_db_path()
os.environ.setdefault("GROUNDWORK_DB", DB)

app = FastAPI(title="Groundwork", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("GROUNDWORK_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    question: str


def _mode(provided_key: str | None = None) -> str:
    """real if a usable Anthropic key exists (server env or per-request BYOK), else mock."""
    if os.environ.get("GROUNDWORK_MOCK") == "1":
        return "mock"
    if provided_key or os.environ.get("ANTHROPIC_API_KEY"):
        return "real"
    return "mock"


def _build_router(provided_key: str | None = None) -> TieredRouter:
    if _mode(provided_key) == "mock":
        from run_demo import mock_responder  # noqa: PLC0415

        return TieredRouter(provider_factory=lambda m: MockProvider(m, responder=mock_responder))
    # BYOK: provided_key (if any) is used for this request only; never stored/logged.
    return TieredRouter(api_key=provided_key or None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": _mode(), "byok": not os.environ.get("ANTHROPIC_API_KEY")}


@app.get("/runs")
def runs(limit: int = 50) -> dict:
    return {"runs": store.list_runs(DB, limit=limit)}


@app.get("/runs/{run_id}")
def run_detail(run_id: int):
    from fastapi import HTTPException  # noqa: PLC0415

    run = store.get_run(DB, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@app.post("/research")
async def research(req: ResearchRequest,
                   anthropic_key: Optional[str] = Header(default=None, alias="X-Anthropic-Key")):
    q: "queue.Queue[dict]" = queue.Queue()
    sentinel = {"type": "__done__"}
    mode = _mode(anthropic_key)

    def run() -> None:
        tracer = Tracer(sink=lambda step: q.put({"type": "step", **step}))
        try:
            orch = Orchestrator(router=_build_router(anthropic_key), tracer=tracer)
            result = orch.run(req.question)
            try:
                run_id = store.save_run(DB, req.question, mode, result)
                result["run_id"] = run_id
            except Exception:  # noqa: BLE001 — persistence is best-effort
                pass
            q.put({"type": "result", "result": result})
        except Exception as e:  # noqa: BLE001 — surface to the client
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(sentinel)

    async def stream():
        loop = asyncio.get_event_loop()
        threading.Thread(target=run, daemon=True).start()
        yield _sse({"type": "start", "question": req.question, "mode": mode})
        while True:
            event = await loop.run_in_executor(None, q.get)
            if event.get("type") == "__done__":
                break
            yield _sse(event)
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
