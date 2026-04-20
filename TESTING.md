# BlockFlow Testing Guide

BlockFlow uses a three-branch promotion model (`dev` → `staging` → `main`) plus a
**mock mode** that short-circuits RunPod calls so the UI can be clicked through
end-to-end without burning GPU credits.

---

## 1. Branch model (IT / ST / UAT analogy)

| Branch    | Environment        | Purpose                                                    | Who merges |
|-----------|--------------------|------------------------------------------------------------|------------|
| `dev`     | local loopback     | Coding / unit tinkering. Lives on each dev machine.        | Agents     |
| `staging` | staging tunnel     | **UAT**: human clicks real UI in mock mode before sign-off | Agents     |
| `main`    | production tunnel  | Live. Real RunPod calls cost money.                        | Human only |

Agents **MUST NOT** push to `main`. Every autonomous change lands on `staging`,
the user tests it via the staging tunnel, then cherry-picks or fast-forwards to
`main` when satisfied.

```bash
# create once, on any machine
git checkout main
git branch dev
git branch staging

# typical day
git checkout dev
# ... edit, commit ...
git push origin dev
git checkout staging && git merge --ff-only dev && git push origin staging
# user tests, then:
git checkout main && git merge --ff-only staging && git push origin main
```

---

## 2. Mock mode (`BLOCKFLOW_MOCK_RUNPOD=1`)

With mock mode on, `backend/services.py::_submit_job` returns a fake
`mock-<hex>` job id, and `_poll_status` returns a canned COMPLETED response
after `BLOCKFLOW_MOCK_DELAY_SEC` seconds (default 1.0). All other pipeline
plumbing — DB writes, job records, WebSocket events, R2 metadata, frontend
polling — runs exactly as in production, so you exercise the **entire stack
except the GPU call**.

Enable:

```bash
# PowerShell (Windows)
$env:BLOCKFLOW_MOCK_RUNPOD = "1"
uv run app.py --port 8100

# bash / zsh
export BLOCKFLOW_MOCK_RUNPOD=1
uv run app.py --port 8100
```

Returned placeholder URLs:

- image: `https://placehold.co/832x1216/1a1a2e/e0e0ff.png?text=MOCK+IMAGE`
- video: `https://placehold.co/832x480/1a1a2e/e0e0ff.mp4?text=MOCK+VIDEO`

Override via `BLOCKFLOW_MOCK_IMAGE_URL` / `BLOCKFLOW_MOCK_VIDEO_URL`.

### What mock mode DOES cover

- Every `/api/m/*` and `/api/*` endpoint end-to-end (HTTP layer, validation,
  DB, response shape)
- Frontend forms, loading states, error branches, result rendering
- Cross-page flows (Gallery → Tools prefill, mobile tab switching)
- Job history list / detail / delete / retry

### What mock mode does NOT cover

- Actual ComfyUI workflow validity (wrong node wiring won't be caught)
- R2 upload of real bytes (placeholder URLs aren't stored)
- LoRA SSH listing (still hits real SSH target)
- Topaz / CivitAI / OpenRouter (those have their own API keys, not mocked)

---

## 3. Ports & staging tunnel

To run staging and production side-by-side on one machine:

| Env        | Frontend port | Backend port | Tunnel                                  |
|------------|---------------|--------------|-----------------------------------------|
| Production | 3000          | 8000         | primary cloudflared tunnel              |
| Staging    | 3100          | 8100         | secondary cloudflared quick tunnel      |

### Start staging locally

```powershell
# Terminal 1 — backend (mock mode)
cd C:\Users\socr0\BlockFlow
$env:BLOCKFLOW_MOCK_RUNPOD = "1"
uv run app.py --port 8100

# Terminal 2 — frontend
cd C:\Users\socr0\BlockFlow\frontend
$env:NEXT_PUBLIC_API_BASE = "http://localhost:8100"
npm run dev -- --port 3100

# Terminal 3 — tunnel (optional, for remote UAT)
cloudflared tunnel --url http://localhost:3100
```

Cloudflare prints a fresh `https://<random>.trycloudflare.com` URL. Share that
with the human for UAT clicks.

---

## 4. L1 – L5 test levels

| Level | Scope                                 | Cost    | Automation        |
|-------|---------------------------------------|---------|-------------------|
| L1    | TypeScript / Python compile           | free    | `npm run build` / `uv run ruff check` |
| L2    | Lint / type check                     | free    | eslint, mypy (opt) |
| L3    | API smoke with curl (mock mode)       | free    | shell script       |
| L4    | UI click-through on staging tunnel    | free    | human              |
| L5    | Single real RunPod generation         | ~¥5-30  | human only         |

Agents finish through **L3** and hand off to the human at L4.

---

## 5. Smoke test script (L3)

```bash
# with mock mode backend running on :8100
BASE=http://localhost:8100
curl -s $BASE/api/m/health | jq
curl -s -X POST $BASE/api/m/outpaint \
  -H 'content-type: application/json' \
  -d '{"image_url":"https://example.com/x.png","prompt":"test","endpoint_id":"mock"}' | jq
# ...add one line per endpoint you touched
```
