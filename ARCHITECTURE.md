# BlockFlow Architecture

## Process model

```
┌──────────────────────────────────────────────────────────────┐
│  uv run app.py                                               │
│                                                              │
│  ├─ uvicorn backend.main:app       (FastAPI, :8000)          │
│  └─ npm run dev                    (Next.js turbopack :3000) │
└──────────────────────────────────────────────────────────────┘
          │                                    │
          ▼                                    ▼
   RunPod Serverless                   User's browser
   endpoint (ComfyUI)                  (desktop or mobile)
```

## Layout

```
BlockFlow/
├── app.py                     Entry: spawns backend + frontend
├── backend/
│   ├── main.py                FastAPI app + router wiring
│   ├── config.py              Env loading, R2, mock-mode flags
│   ├── services.py            RunPod submit/poll + mock shortcuts
│   ├── m_routes.py            Mobile `/api/m/*` routes + workflow builders
│   ├── r2_routes.py           R2 gallery endpoints
│   ├── m_store.py             Cost log, presets, batch, schedule
│   ├── db.py / state.py       SQLite run history + cache locks
│   └── routes.py              Legacy desktop `/api/*` pipeline routes
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx           Desktop pipeline editor entry
│       │   ├── tools/page.tsx     Phase 12/14/16 panels (PC)
│       │   ├── gallery/page.tsx   R2 gallery + send-to-Tools
│       │   ├── m/page.tsx         Mobile tabbed UI (all features)
│       │   └── generate/page.tsx  (shim; redirects)
│       ├── components/
│       │   ├── nav-bar.tsx        Top nav (Tools, Gallery, ...)
│       │   └── pipeline/custom_blocks/generated/*.tsx
│       └── lib/
│           ├── api.ts             fetch wrappers + R2 helpers
│           └── comfygen-overrides.ts
├── flows/                     User-saved pipeline JSON (git-tracked)
├── scripts/
│   └── smoke_test_mock.ps1    L3 smoke test for mock mode
└── data/                      Runtime cost log (gitignored)
```

## Request flow — mobile `/api/m/outpaint`

```
browser  ─POST /api/m/outpaint─▶  FastAPI (m_routes.m_outpaint)
                                      │
                                      ├─ build_illustrious_outpaint_workflow()
                                      │   (ComfyUI graph dict)
                                      │
                                      ├─ services._submit_job()
                                      │     │
                                      │     ├─[if MOCK_RUNPOD]─▶ return mock-<hex>
                                      │     │
                                      │     └─[else]──▶ POST runpod.ai/v2/{ep}/run
                                      │
                                      ├─ m_store.log_cost()
                                      │
                                      └─ JSON{ ok, remote_job_id, est_cost_usd }
                                         │
                                         ▼
                              browser polls /api/m/status/{remote_job_id}
                                         │
                                         ├─[mock / id starts mock-]─▶ _mock_status_response()
                                         │
                                         └─[else]─▶ RunPod GET /status/{id}
```

## Mock mode

`BLOCKFLOW_MOCK_RUNPOD=1` short-circuits two functions:

| Function | Real behavior | Mock behavior |
|---|---|---|
| `services._submit_job` | HTTP POST to RunPod `/run` | Returns `mock-<uuid[:12]>`, registers job locally |
| `services._poll_status` loop | HTTP GET `/status` | Returns IN_PROGRESS until `MOCK_DELAY_SEC`, then COMPLETED |
| `m_routes.m_status` | HTTP GET `/status` | Same, via `_mock_status_response()` |
| `m_routes.m_cancel` | HTTP POST `/cancel` | Returns `{status: CANCELLED}` |

A fake placeholder image/video URL replaces the real RunPod output.
`_is_video_job()` peeks at workflow node class types to pick the right kind.

Unknown mock ids (jobs from a previous process) resolve as already-COMPLETED
so the frontend doesn't hang.

## Branch model

- `dev`     — autonomous/local coding
- `staging` — UAT, mock mode on alt ports (3100/8100)
- `main`    — production, real RunPod calls

See `TESTING.md` for L1-L5 test levels and promotion workflow.

## Key endpoints (non-exhaustive)

### Mobile API (`/api/m/*`)
- `POST /generate`          — Z-Image / Illustrious generate
- `POST /batch_generate`    — batch submit
- `POST /outpaint`          — **Phase 12** ImagePadForOutpaint + inpaint
- `POST /character_sheet`   — **Phase 14** multi-view turnaround (2048x1024)
- `POST /ltx_video`         — **Phase 16** LTX T2V or I2V
- `POST /generate_charaip`  — IP-Adapter reference generation
- `POST /adetailer`         — face/hand detailer
- `POST /generate_controlnet` — ControlNet Canny
- `POST /inpaint`           — masked inpaint
- `GET  /status/{id}`       — poll job
- `POST /cancel/{id}`       — cancel job
- `GET  /cost`              — aggregate cost summary
- `GET  /inventory`         — RunPod models/LoRAs

### Desktop API (`/api/*`)
- `GET  /flows`             — saved pipeline list
- `POST /flows/{id}/run`    — execute pipeline
- `GET  /runs`              — run history
- `GET  /feature-flags`     — UI feature toggles
- R2 gallery: `GET /api/r2/images`, `GET /api/r2/image/{key}`

## Storage

- **Generated media** → RunPod output → tmpfiles.org (1h TTL) → R2 bucket
- **Run history** → `run_history.db` (SQLite, local)
- **Job history** → `job_history.json` (for WebSocket reconnect)
- **Cost log** → `data/m_cost_log.jsonl` (gitignored)
- **Presets / schedules / publications** → `m_store.py` JSON files
