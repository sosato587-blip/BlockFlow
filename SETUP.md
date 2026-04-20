# BlockFlow Setup Guide

Zero-to-running walkthrough for a fresh machine.

## 1. Prerequisites

- **Python 3.12+** (uv recommended: `pip install uv`)
- **Node.js 20+** and `npm`
- A **RunPod Serverless** endpoint with the ComfyUI handler image
  (see `CLAUDE.md` → satoso2/comfyui-serverless:v9-delete)
- Optional: **Cloudflare R2** bucket for persistent image/video storage
- Optional: **OpenRouter** API key for Prompt Writer
- Optional: **Topaz Labs** API key for upscaling blocks

## 2. Clone & env

```bash
git clone https://github.com/sosato587-blip/BlockFlow.git
cd BlockFlow
cp .env.example .env
```

Edit `.env`:

```ini
# Required
RUNPOD_API_KEY=rpa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RUNPOD_ENDPOINT_ID=xio27s12llqzpa          # your endpoint id
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx   # for Prompt Writer

# Optional: Cloudflare R2 (for gallery persistence)
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=your-bucket
R2_PREFIX=comfy-gen/outputs/
```

## 3. Install & run

```bash
# installs frontend deps on first run
uv run app.py
```

The launcher starts:
- FastAPI backend on `http://127.0.0.1:8000`
- Next.js frontend on `http://127.0.0.1:3000`

Open http://localhost:3000 (auto-opens on Windows).

## 4. (Optional) Remote access via Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:3000
```

Prints a `https://<random>.trycloudflare.com` URL. Mobile devices on the same
internet can reach the UI through it.

## 5. (Optional) Staging environment for UAT

To run a second instance on the same machine without touching production:

```powershell
# PowerShell — staging on :3100 / :8100, mock mode on (no GPU cost)
$env:BLOCKFLOW_MOCK_RUNPOD = "1"
$env:BACKEND_PORT  = "8100"
$env:FRONTEND_PORT = "3100"
uv run app.py
```

See `TESTING.md` for the full UAT workflow (dev → staging → main branch promotion).

## 6. Verify everything works

```bash
# health
curl http://localhost:8000/api/m/cost
# expect: {"ok":true,"total_usd":0.0,...}

# (staging-only, mock mode) end-to-end generation
curl -X POST http://localhost:8100/api/m/generate \
  -H 'content-type: application/json' \
  -d '{"prompt":"test","negative_prompt":"","width":832,"height":1216,"steps":25,"batch_size":1}'
# expect: {"ok":true,"remote_job_id":"mock-...","est_cost_usd":...}
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401 no token provided` on generate | `RUNPOD_API_KEY` not set / wrong |
| `endpoint_id required` on Tools page | Fill the Endpoint ID field at top of `/tools` (saved locally) |
| Port 8000 already in use | Kill old `uvicorn` (`taskkill //PID <pid> //F` on Windows) |
| Frontend build fails | `cd frontend && rm -rf node_modules .next && npm install` |
| R2 uploads silently fail | Check `R2_ACCESS_KEY`/`R2_SECRET_KEY` in `.env`; hardcoded defaults were removed for security |
| Mock mode jobs stuck at IN_PROGRESS | Upgrade — fixed in Phase C: unknown ids resolve as COMPLETED |
