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

## Cost note & BYOK

A public live demo calls Claude on every request. Two safe ways to expose one:

- **Bring-your-own-key (recommended for a public demo):** deploy the backend
  **without** `ANTHROPIC_API_KEY`. Visitors paste their own key in the dashboard;
  it's sent per request as the `X-Anthropic-Key` header, used only for that
  request, and never stored or logged. With no visitor key the demo runs in
  offline mock mode. Zero cost and zero abuse surface for you. The dashboard
  shows a "live models" / "offline demo" badge accordingly.
- **Your key + caps:** set `ANTHROPIC_API_KEY` on the backend and add rate
  limiting / a spend cap. Smoother UX, but you pay for usage.

Either way, set a server `TAVILY_API_KEY` to enable live web search (BYOK covers
the model key; search stays server-configured).
