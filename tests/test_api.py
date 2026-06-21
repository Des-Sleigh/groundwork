"""API integration tests — real FastAPI endpoints, offline mock mode, no key.

Exercises the SSE research stream end-to-end (the agent actually runs, in mock
mode) plus persistence and the history endpoints.
"""

import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

# Configure before importing the app (it reads these at import time).
os.environ["GROUNDWORK_MOCK"] = "1"
os.environ["GROUNDWORK_DB"] = tempfile.mktemp(suffix=".db")

from fastapi.testclient import TestClient  # noqa: E402

from api.server import app  # noqa: E402

client = TestClient(app)


def test_health_reports_mock_mode():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "mode": "mock"}


def test_research_streams_steps_and_result():
    r = client.post("/research", json={"question": "How is AI used in logistics forecasting?"})
    assert r.status_code == 200
    body = r.text
    assert '"type": "start"' in body
    assert '"type": "step"' in body       # trajectory streamed
    assert '"type": "result"' in body     # final result delivered
    assert '"type": "done"' in body       # stream terminated cleanly


def test_runs_history_and_detail():
    # The run above is persisted; history should have at least one entry.
    runs = client.get("/runs").json()["runs"]
    assert len(runs) >= 1
    rid = runs[0]["id"]
    detail = client.get(f"/runs/{rid}").json()
    assert detail["question"]
    assert "result" in detail and "trace" in detail


def test_missing_run_404():
    assert client.get("/runs/99999999").status_code == 404
