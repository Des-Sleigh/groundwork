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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.providers import MockProvider, TieredRouter
from core.tracing import Tracer
from orchestrator.loop import Orchestrator

app = FastAPI(title="Groundwork", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("GROUNDWORK_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    question: str


def _is_mock() -> bool:
    return os.environ.get("GROUNDWORK_MOCK") == "1" or not os.environ.get("ANTHROPIC_API_KEY")


def _build_router() -> TieredRouter:
    if _is_mock():
        from run_demo import mock_responder  # noqa: PLC0415

        return TieredRouter(provider_factory=lambda m: MockProvider(m, responder=mock_responder))
    return TieredRouter()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": "mock" if _is_mock() else "real"}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@app.post("/research")
async def research(req: ResearchRequest):
    q: "queue.Queue[dict]" = queue.Queue()
    sentinel = {"type": "__done__"}

    def run() -> None:
        tracer = Tracer(sink=lambda step: q.put({"type": "step", **step}))
        try:
            orch = Orchestrator(router=_build_router(), tracer=tracer)
            result = orch.run(req.question)
            q.put({"type": "result", "result": result})
        except Exception as e:  # noqa: BLE001 — surface to the client
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(sentinel)

    async def stream():
        loop = asyncio.get_event_loop()
        threading.Thread(target=run, daemon=True).start()
        yield _sse({"type": "start", "question": req.question,
                    "mode": "mock" if _is_mock() else "real"})
        while True:
            event = await loop.run_in_executor(None, q.get)
            if event.get("type") == "__done__":
                break
            yield _sse(event)
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
