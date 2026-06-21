# FastAPI agent backend (deploy target: Render).
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching.
COPY pyproject.toml README.md ./
COPY core ./core
COPY mcp_server ./mcp_server
COPY research_agent ./research_agent
COPY orchestrator ./orchestrator
COPY api ./api
COPY corpus ./corpus
COPY redteam ./redteam
COPY run_demo.py ./

RUN pip install --no-cache-dir ".[real,api]"

ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (set by the host) is expanded.
CMD uvicorn api.server:app --host 0.0.0.0 --port ${PORT}
