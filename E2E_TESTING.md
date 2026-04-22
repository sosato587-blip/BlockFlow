# E2E Testing (Playwright)

Zero-GPU-cost smoke tests that exercise the running BlockFlow stack in **mock mode**.

## What's tested

- Home, `/m` mobile, and `/tools` pages render without 5xx.
- API contracts on the new base-model taxonomy:
  - `/api/blocks/base_model_selector/families` returns 7 families.
  - `/api/blocks/lora_selector/loras` includes `grouped_high` / `grouped_low` / `families`.
  - `/api/blocks/lora_selector/loras?family=illustrious` filters correctly.
- `/api/m/ltx_dl_info` returns the LTX 2B download spec (post-fp8 cleanup).
- `/api/m/ltx_video` responds `ok: true` with a job id in mock mode.

## One-time setup

```powershell
cd frontend
npm install            # installs @playwright/test
npx playwright install chromium    # one-time ~500MB browser DL
```

## Spinning up the staging stack

Playwright talks to `http://localhost:3100` by default (the staging port). Start it separately:

```powershell
cd C:\Users\socr0\BlockFlow
$env:BLOCKFLOW_MOCK_RUNPOD = "1"
$env:BACKEND_PORT = "8100"
$env:FRONTEND_PORT = "3100"
uv run app.py
```

Leave that terminal running — don't mix prod (3000/8000) with staging.

## Run tests

```powershell
cd frontend
npm run test:e2e          # headless
npm run test:e2e:ui       # Playwright UI
```

## CI notes

- `PLAYWRIGHT_BASE_URL` env var overrides the default base URL.
- The mock-mode LTX test will fail if the server is running without `BLOCKFLOW_MOCK_RUNPOD=1`, which is the whole point — it's a safety net against accidentally pointing tests at a live RunPod endpoint.

## What's NOT tested (yet)

- Full pipeline execution across multiple custom blocks (Base Model Selector → LoRA Selector → comfy_gen).
- LLM-dependent blocks (prompt_writer / i2v_prompt_writer) — these hit OpenRouter; add fixture-based tests with `test.describe.skip` when there's no API key.
- WAN I2V + Fun Control — require RunPod; left to manual QA.
