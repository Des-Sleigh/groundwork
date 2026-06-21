# Deploying Groundwork

Two pieces: the **FastAPI agent backend** (Render) and the **Next.js dashboard**
(Vercel). The demo shown in the README is a recorded walkthrough, so there's no
always-on public endpoint burning API credits — deploy when you want a live one.

## Backend — Render

1. Push this repo to GitHub (done).
2. On [render.com](https://render.com): **New → Blueprint**, point it at the repo.
   Render reads `render.yaml` and builds the `Dockerfile`.
3. In the service's **Environment**, set:
   - `ANTHROPIC_API_KEY` (required)
   - `TAVILY_API_KEY` (optional — enables live web search; without it the API
     uses the offline fixture corpus)
   - `GROUNDWORK_CORS_ORIGINS` → your Vercel URL (e.g. `https://groundwork.vercel.app`)
4. Deploy. Health check: `GET /health` → `{"status":"ok","mode":"real"}`.

Local equivalent:

```bash
pip install -e ".[real,api]"
uvicorn api.server:app --port 8000
```

## Frontend — Vercel

1. On [vercel.com](https://vercel.com): **Add New → Project**, import the repo.
2. Set **Root Directory** to `web`.
3. Environment variable: `NEXT_PUBLIC_API_URL` = your Render backend URL.
4. Deploy (Vercel auto-detects Next.js).

Local equivalent:

```bash
cd web && npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

## Offline (no keys, no deploy)

```bash
GROUNDWORK_MOCK=1 uvicorn api.server:app --port 8000   # backend in mock mode
cd web && npm run dev                                    # dashboard
```

The dashboard shows a "offline demo" badge in mock mode and "live models" when
the backend has a key.

## Cost note

A public live demo calls Claude (and a search API) on every request. If you
expose one, add rate limiting / a spend cap, or keep it behind the recorded
walkthrough as the default public artifact.
