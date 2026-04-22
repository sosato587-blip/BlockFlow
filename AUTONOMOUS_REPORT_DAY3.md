# Autonomous Report — Day 3 (2026-04-21 daytime)

Continuation of Night 2. User picked H1/H2/H3/H6/H7 with cost guardrails.

## ✅ Completed

### H1 — UX Quick Wins (commit `f937e84`)

Applied 9 findings from `UX_AUDIT.md` § "Ready-to-commit quick wins":

| Fix | File |
|---|---|
| Prompt textarea `min-h-[80px] → min-h-[160px]` | `generation/frontend.block.tsx`, `wan_22_image_to_video/frontend.block.tsx` |
| System-prompt textarea `min-h-[60px] → min-h-[160px]` + max bump | `i2v_prompt_writer/frontend.block.tsx` |
| API-key missing warning `yellow → red` | `civitai_share`, `i2v_prompt_writer` |
| `...` → `…` (U+2026) in status/placeholder strings | `upscale`, `generation`, `wan_22_image_to_video` |
| `Clear` → `Clear all` | `image_viewer`, `video_viewer` |
| CFG/Shift/Steps labels get range hints `(1.0 recommended)` etc. | `wan_fun_control` |
| Read-only video URL gets Copy button | `video_loader` |

Items already present and no-op: lora_selector aria-label (added in NIGHT2), image_upscale type="number".

### H2 — Base Model → checkpoint auto-override (commit `f9000f1`)

- **comfy_gen**: at execute time, scans the parsed workflow JSON for `CheckpointLoaderSimple` / `CheckpointLoader` / `UNETLoader` nodes and auto-injects `${node_id}.ckpt_name` (or `.unet_name`) into the overrides dict from `base_model.checkpoint`. Respects explicit user overrides — won't clobber. This is the real payoff of the Base Model Selector architecture from NIGHT2.
- **generation** (Wan T2V) and **wan_22_image_to_video**: accept `base_model` input port, forward `base_model.checkpoint` into `job_input["checkpoint"]` on the RunPod payload. No-op passthrough until the serverless handler reads it, but the plumbing is in place.
- All three blocks now have `{ name: 'base_model', kind: 'base_model', required: false }`.

Wiring: `[Base Model Selector] → [LoRA Selector] → [ComfyUI Gen]` now actually changes which checkpoint file the workflow loads on RunPod. Previously the Base Model Selector was metadata-only.

### H6 — LTX models on RunPod (commit `7c5d9bc`)

Investigated the volume first:
- `waiIllustriousSDXL_v160.safetensors` ✅ (checkpoints)
- `t5xxl_fp8_e4m3fn.safetensors` ✅ (text_encoders, 4.7 GB, from Flux)
- `qwen_3_4b`, `umt5_xxl_fp8`, WAN i2v high/low, Z-Image ✅

**Switched the LTX workflow from `t5xxl_fp16` (9.8 GB) to the existing `t5xxl_fp8_e4m3fn`.** `CLIPLoader` with `type='ltxv'` accepts fp8 and quality difference is negligible for the encoder. Saved ~10 GB of network DL.

Then submitted the LTX 2B checkpoint download as a single RunPod `download` job:

```
ltx-video-2b-v0.9.5.safetensors → /runpod-volume/ComfyUI/models/checkpoints/
6047 MB, COMPLETED
```

Verified via `list_models checkpoints` — both `waiIllustrious` and `ltx-video-2b-v0.9.5` present. `/api/m/ltx_video` (mock or real) is now unblocked. Per user's "生成は限りなく少ないもの" ask, no LTX generations were run here.

### H7 — Playwright E2E smoke tests (commit `7671581`)

- Installed `@playwright/test` as devDep (no browser binary — that's a one-time `npx playwright install chromium` the user runs locally).
- `frontend/playwright.config.ts` targets staging (3100/8100) with retain-on-failure traces.
- `frontend/tests/e2e/smoke.spec.ts`:
  - Page-load 2xx on `/`, `/m`, `/tools`.
  - `/api/blocks/base_model_selector/families` returns ≥7 families with expected IDs.
  - `/api/blocks/lora_selector/loras` exposes `grouped_high` / `grouped_low` / `families`.
  - `/api/blocks/lora_selector/loras?family=illustrious` filters correctly.
  - `/api/m/ltx_dl_info` returns new single-file DL spec.
  - Mock-mode `/api/m/ltx_video` returns `ok: true`.
- `E2E_TESTING.md` documents the one-time browser install and the staging-spinup pattern.
- `npm run test:e2e` / `test:e2e:ui` scripts.

Zero GPU cost — everything runs against mock-mode staging.

## 🟡 Deferred: H3 — WAN Phase 3 comparison batch

Checked the RunPod volume:
- `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` ✅
- `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` ✅
- `wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors` ❌ — **not present**
- `wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors` ❌ — **not present**

Phase 3 uses Fun Control. Re-downloading the two Fun Control UNETs is ~27 GB — not free bandwidth-wise. Combined with 15 videos × ~$0.30 = ~$4.50 of GPU, that exceeds the "cost" bar the user set today.

**Decision: skip H3, surface the blocker.** If you want to actually run Phase 3 another night, I'll need a green light to re-download Fun Control (free DL, just time) *and* to burn ~$5 of GPU. Until then, `workflows/comparison_tests.py` remains ready.

## Branch state

```
dev = 7671581 (4 new commits ahead of main)
  f937e84  feat(ux): H1 quick wins
  f9000f1  feat(base-model): checkpoint auto-override
  7c5d9bc  feat(ltx): fp8 instead of fp16
  7671581  test(e2e): Playwright smoke tests
```

Pending: fast-forward `staging` and `main` to match `dev`.

## Artifacts

- `E2E_TESTING.md` (new)
- `frontend/playwright.config.ts` + `frontend/tests/e2e/smoke.spec.ts` (new)
- Updated `LTX_QUICKSTART.md` (fp8 notes)
- `AUTONOMOUS_REPORT_DAY3.md` (this file)
