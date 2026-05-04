# sgs-ui

Local-only pipeline UI for submitting video/image generation jobs to RunPod serverless endpoints.

---

## 🔴🔴🔴 Pre-Task Charter — STOP and read this BEFORE any non-trivial work

This codebase has accumulated architectural decisions across many sessions
and many Claude instances. Each new Claude that walks in **without loading
these decisions repeats the same patch-after-patch mistakes** the user has
already paid for several times.

The rule is simple. **Before you touch anything beyond a typo / log line /
comment**, you MUST do the following, IN ORDER:

1. **Read [`ARCHITECTURE.md`](ARCHITECTURE.md)** in full (5 min). It
   describes the process model and module layout.

2. **Read the relevant section(s) of
   [`docs/SUBSYSTEMS.md`](docs/SUBSYSTEMS.md)**. This file lists, per
   subsystem: owner files, input/output contracts, design assumptions,
   common gotchas, and the things you must NOT touch without escalation.

3. **Skim `docs/decisions/`** for any ADR (Architecture Decision Record)
   whose title is related to the area you'll modify. ADRs explain *why*
   the current shape is the way it is.

4. **Open the actual current code** for the file(s) you plan to modify
   and read at least the top 100 lines plus the surrounding 50 lines of
   anything you intend to change. Do not modify code you have not
   read in this session.

5. **State your understanding back to the user before you write any code.**
   Your first response in any non-trivial task must contain:
   - **"Current design as I understand it: …"**
   - **"Design assumptions I'm relying on: …"**
   - **"Files I plan to touch: …"**
   - **"Risks / things this might break: …"**
   Then stop and wait for the user's "go" before you call Edit / Write /
   Bash that mutates state.

### What counts as "non-trivial"

Treat ANY of the following as non-trivial — Pre-Task Charter applies:

- Editing `custom_blocks/*/frontend.block.tsx` or `*/backend.block.py`
- Editing `backend/m_routes.py`, `backend/services.py`, `backend/base_models.py`
- Editing `frontend/src/app/m/page.tsx` (the mobile monolith)
- Editing the Docker handler / Dockerfile under `docker-comfyui/`
- Adding or changing API contracts (request/response shapes)
- Anything that affects the worker image (rebuild + push + RunPod recycle)
- Anything that would download or delete files on the RunPod network volume
- Anything the user asks for that touches more than one file

You may skip the Charter for: typo fixes, single-line comment additions,
markdown-only doc edits, and `git status` / read-only inspection.

### Why this exists

Recent failures that this Charter is designed to prevent:

- **Wan 2.2 Animate v1 vs v2 mismatch (2026-05-03)** — desktop Claude deleted
  the on-disk v1 file because it didn't read `wan_animate/workflow_template.json`
  first; that template explicitly targeted v1 by filename.
- **LoRA classifier coverage gap (2026-05-03)** — desktop Claude assembled an
  Illustrious LoRA recommendation list without running `classify_lora()` against
  the actual on-disk inventory; 22 of 48 files turned out to be invisible in the
  family-filtered UI.
- **Prompt UI workflow-driven design (recurring)** — multiple Claude sessions
  proposed prompt-related fixes without acknowledging that the entire prompt UI
  is parsed from the loaded workflow's `CLIPTextEncode` nodes; an empty parse
  yields zero textareas. The user has flagged this as confusing UX more than
  once.

The pattern is always the same: jump to solution mode without context-loading.
The Charter exists to break that habit.

### Who this binds

EVERY Claude instance — Desktop Code, Web, Mobile, agentic, autonomous.
There is no "I'm just a quick session" exemption. The user has paid the price
for this several times and asked for the rule on 2026-05-03.

---

## Tech Stack

- **Frontend**: Next.js 16, React 19, shadcn/ui, Tailwind CSS (dark theme only)
- **Backend**: FastAPI, uvicorn
- **Launch**: `uv run app.py` starts both FastAPI (:8000) and Next.js (:3000)

## Pipeline System

The `/generate` page uses a linear left-to-right pipeline with a tree branching model.

- **Block** is the canonical term (not node, step, or stage)
- One global "Run Pipeline" button — no per-block actions
- Accumulator data model: outputs collected by `PortKind`, resolved as inputs to downstream blocks
- Execute functions receive fresh `inputs` parameter and an `AbortSignal` from the pipeline runner
- **Parallel pipelines**: Multiple tabs can run pipelines simultaneously. Each tab's PipelineProvider is always mounted. Cancellation is tab-scoped (only aborts polls for that tab's blocks). A floating job manager appears when 2+ tabs are running.
- **Pipeline cancellation**: AbortSignal propagated to execute functions. Blocks like ComfyGen register abort listeners to cancel backend jobs (kills subprocess + cancels remote RunPod job).
- **Job manager**: Floating panel (top-right) appears when 2+ tabs are running simultaneously. Shows each running tab's name, current block, and a per-tab stop button. Collapsible.

## ComfyGen Block

The `comfy_gen` block submits ComfyUI workflows to a RunPod serverless endpoint.

- **LoRA detection**: Automatically detects `LoraLoader` and `LoraLoaderModelOnly` nodes in parsed workflows. Shows a collapsible "LoRAs" section with per-LoRA name override (dropdown or text input) and strength sliders.
- **LoRA list caching**: Dual-layer cache — backend in-memory + frontend localStorage (`comfygen_lora_cache`), both with 24h TTL. Fetching spawns a RunPod job via `comfy-gen list loras` (up to 90s). Stale cache auto-prompts refresh.

## Adding a Block

1. Create `custom_blocks/<slug>/frontend.block.tsx` exporting `blockDef: BlockDef`
2. Optionally add `custom_blocks/<slug>/backend.block.py` exporting `router: APIRouter`
3. Registration is automatic via codegen (`npm run predev`)

## Block Sizes

sm (280x220, blue), md (360x320, emerald), lg (440x460, violet), huge (540x580, amber)

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Single entrypoint, starts FastAPI + Next.js |
| `frontend/src/lib/pipeline/` | Registry, types, pipeline-context, tree-utils |
| `frontend/src/components/pipeline/` | Pipeline view, block card, chain renderer |
| `custom_blocks/` | Self-contained block definitions |
| `backend/main.py` | FastAPI app, auto-loads block sidecars |
| `backend/routes.py` | Shared routes: flows + runs only |
| `frontend/src/components/pipeline/job-manager.tsx` | Floating job manager for parallel pipeline runs |

## Conventions

- Dark theme only (shadcn/ui, `class="dark"` on `<html>`)
- URL-state routing: filters/sort in URL search params
- Block API routes: `/api/blocks/<slug>/...` only
- No Playwright testing — user tests manually, use `npm run build` for verification
