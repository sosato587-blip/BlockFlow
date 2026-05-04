# Subsystems Reference

**Purpose**: Per-subsystem contracts. Read the relevant section *before*
modifying any code in that subsystem. This is the file the Pre-Task
Charter (`CLAUDE.md`) requires you to consult.

**Audience**: Every Claude instance (Desktop Code / Web / Mobile / agentic).

**Maintenance rule**: If you change a subsystem's behaviour or invariant,
update its section here in the SAME commit. Drift between code and this
file is the failure mode this file exists to prevent.

---

## Table of contents

| Subsystem | One-line summary |
|---|---|
| [ComfyGen — Workflow Parsing](#comfygen--workflow-parsing) | Turns uploaded ComfyUI JSON into UI controls |
| [ComfyGen — Prompt UI](#comfygen--prompt-ui) | Currently workflow-driven (ADR 0001); known UX gap |
| [ComfyGen — Inline LoRA Picker](#comfygen--inline-lora-picker) | Shared component used by `/generate` ComfyGen + `/m` |
| [LoRA Classifier (`base_models.py`)](#lora-classifier-base_modelspy) | Filename → family routing for the family-filtered LoRA UI |
| [LoRA list cache layers](#lora-list-cache-layers) | SSH primary → comfy_gen_info_cache.json fallback → in-memory |
| [Mobile UI (`/m`)](#mobile-ui-m) | The 3,600-line monolith. Dual-implementation rule applies |
| [Pipeline Runtime (frontend)](#pipeline-runtime-frontend) | Block registry + execute() + AbortSignal |
| [Workflow Builders (`m_routes.py`)](#workflow-builders-m_routespy) | Mobile/`/m` builds workflow JSON server-side |
| [RunPod Worker Handler](#runpod-worker-handler) | Vendored Hearmeman code + the aria2c→curl shim |
| [Worker Image / Dockerfile](#worker-image--dockerfile) | `satoso2/comfyui-serverless`, build/push/recycle |
| [Network volume layout](#network-volume-layout) | What goes where on `/runpod-volume/ComfyUI/models/` |
| [R2 / tmpfiles storage](#r2--tmpfiles-storage) | How generated media reaches the user |
| [Wan Animate scaffolding](#wan-animate-scaffolding) | Web-Claude-built block; v1/v2 mismatch unresolved |

---

## ComfyGen — Workflow Parsing

**Owner files**:
- `custom_blocks/comfy_gen/backend.block.py` — `_detect_*` helpers, `parse-workflow` route (line ~1574)
- `custom_blocks/comfy_gen/frontend.block.tsx` — calls `/api/blocks/comfy_gen/parse-workflow` then stores results in session state

**Source of truth**: the parsed payload returned by `parse-workflow` —
`{load_nodes, ksamplers, text_overrides, resolution_nodes, frame_counts,
ref_video, lora_nodes, output_type}`. Every UI section in the ComfyGen
block reads from one of these arrays.

**Design assumptions**:
1. **API-format JSON only**. ComfyUI exports two JSON shapes: API format
   (top-level dict keyed by node id with `class_type` + `inputs`) and
   graph/UI format (`{nodes:[…], links:[…]}`). The parser **explicitly
   rejects** graph format with a 400 error — see line ~1583. Users must
   re-export from ComfyUI with "Save (API Format)" in Dev Mode.
2. **No per-block override of detection**. If a node isn't on the
   `_LORA_CLASS_TYPES` set (only `LoraLoader` + `LoraLoaderModelOnly`
   today), it is invisible to the LoRA picker. Wan-style stacks that use
   a different class will silently miss.
3. **`is_negative` heuristic**: text overrides are tagged `is_negative`
   when their CLIPTextEncode output flows into the `negative` input of a
   downstream KSampler. The flag drives the "Show negative prompts"
   toggle described below.

**Common gotchas**:
- A workflow with **0 detected text overrides** renders **0 textareas**.
  The user sees no prompt UI. This is not a bug in the parser — see
  ADR 0001 and the "Prompt UI" subsection.
- The same applies to LoRA loaders: **0 detected → no inline picker**,
  banner reads "no LoRA loader nodes — inline LoRA picks will be ignored".
- The `_meta.title` of a node provides the user-friendly label. Workflows
  without titles display the class_type instead.

**DO NOT** widen `_LORA_CLASS_TYPES` without checking that the new class
also accepts `lora_name` / `strength_model` inputs. Adding a class with a
different shape will crash the override builder downstream.

**Safe extension path**:
- New optional inputs → add a `_detect_<thing>` helper, return it from
  `parse-workflow`, render in `frontend.block.tsx`. No rewrites needed.

---

## ComfyGen — Prompt UI

**Owner files**:
- `custom_blocks/comfy_gen/frontend.block.tsx` — lines ~2084-2200 render
  the textareas; lines ~1521-1525 compute `visibleTextOverrides` and
  apply the negative-prompt filter

**Current design**: the prompt UI is **workflow-driven**. Each
`CLIPTextEncode.text` input detected by `parse-workflow` becomes one
textarea. Per ADR 0001:

```
parse-workflow  →  text_overrides[]  →  one Textarea per entry
0 detected      →  0 Textareas       →  no prompt UI shown
```

**Known UX gap**: This shape feels backwards from the user's mental
model ("I want to write a prompt; the workflow is implementation
detail"). The user has flagged it more than once. ADR 0002 supersedes
this design with an "always-on" approach — read it before changing the
prompt UI further.

**`showNegativePrompts` toggle** (introduced 2026-04-XX, commit
`f6c170e`): when off (default), `is_negative=true` overrides are
filtered out of the rendered list. When on, they appear with a
`(negative)` label. This was added to declutter the UI for users who
rarely edit the negative prompt; it is **not** a fix for the 0-detected
case.

**DO NOT**:
- Drop the `showNegativePrompts` state without a migration — existing
  user session state references the key. See ADR 0002 for the
  migration approach.
- Move text-override rendering inside a `CollapsibleSection` whose
  default state is collapsed. The user already loses the prompt when it
  doesn't render; hiding it inside a collapsed section makes it worse.

**Safe extension path**:
- ADR 0002 (always-on prompt) is the agreed forward direction. Implement
  by adding an *implicit* fallback override when the parser returns 0
  text fields, so the existing render loop "just works" with one
  always-present positive entry.

---

## ComfyGen — Inline LoRA Picker

**Owner files**:
- `frontend/src/components/lora/InlineLoraPicker.tsx` — shared component
- `frontend/src/lib/lora-mapping.ts` — pure heuristic, mirrored in
  `backend/lora_mapping.py`
- Used from: `custom_blocks/comfy_gen/frontend.block.tsx` (desktop) and
  `frontend/src/app/m/page.tsx` (mobile)

**Source of truth**: the picker takes High / Low arrays of
`{name, strength}` and emits override map entries via
`computeInlineLoraOverrides()`. The 5-case heuristic
(0 / 1 / 2-labeled / 2-unlabeled / >2 loaders) is documented in the
TS source and parity-tested in pytest.

**Design assumption**: the workflow's LoRA loader nodes have already
been parsed. The picker maps picks onto detected node ids; with **0
loaders detected, picks are silently ignored** and the warning banner
fires.

**Dual-implementation note**: If you change the picker prop API or its
override-shape, **both** the desktop ComfyGen block and `m/page.tsx`
must be updated in the same commit. CLAUDE.md "Dual-Implementation
Rule" applies.

---

## LoRA Classifier (`base_models.py`)

**Owner files**:
- `backend/base_models.py` — `FAMILIES`, `KNOWN_CHECKPOINTS`,
  `_LORA_OVERRIDES`, `_LORA_PATTERNS`, `classify_lora()`,
  `group_loras_by_family()`, `family_summary()`
- `tests/test_base_models.py` — 20 cases including 2026-05-03 audit
  regressions

**Source of truth**: `classify_lora(filename) → family_id | UNCLASSIFIED`.
Everything family-related (UI dropdowns, `lora_selector` block, mobile
UI's family filter) calls this directly or transitively.

**Design assumptions**:
1. **Filename-only classification** — no network calls, no metadata
   probing. Fast and offline-safe but brittle to creative naming.
2. **`UNCLASSIFIED` LoRAs are dropped from family-filtered UIs**, not
   shown under an "Other" bucket. Add to `_LORA_OVERRIDES` if you need
   a specific file to appear; widen `_LORA_PATTERNS` if a general
   pattern catches multiple files.
3. **`\b` does not work after underscores** in Python regex (`_` is a
   word char). The 2026-05-03 audit fix uses
   `(?:^|[_\.\- ])` as the prefix-anchor instead. Don't revert to `\b`.
4. **Order matters** — patterns are evaluated top-to-bottom; first match
   wins. Override map is checked before patterns.

**Common gotchas**:
- A new LoRA file that doesn't match any pattern is silently invisible
  in the UI. The 2026-05-03 audit found 22/48 files were in this state.
  Run `classify_lora()` against the actual `list_models` output any
  time you add files.
- `KNOWN_CHECKPOINTS` is for the *checkpoint* picker, not LoRAs. Do not
  add LoRAs there.

**Safe extension path**:
- New family: add a `BaseModelFamily` to `FAMILIES` AND at least one row
  in `KNOWN_CHECKPOINTS` (otherwise `family_summary()` filters it out
  for being empty), AND a `_LORA_PATTERNS` entry, AND tests.
- New override: lowercase filename → family in `_LORA_OVERRIDES`.

---

## LoRA list cache layers

**Owner files**:
- `backend/services.py` — `_get_loras()`, `_run_lora_ssh_command()`,
  `_read_comfy_gen_lora_cache()`
- `state.py` — `LORA_CACHE`, `LORA_CACHE_LOCK`
- `comfy_gen_info_cache.json` (mini PC, BlockFlow root) — disk cache

**Order of resolution** (high → low priority):
1. **In-memory cache** (`state.LORA_CACHE`) with TTL
   (`LORA_LIST_CACHE_TTL_SEC`). Hits unless `refresh=True` or stale.
2. **SSH probe** of the host pointed at by `LORA_SOURCE_SSH_TARGET` env
   var. Production / multi-server setups.
3. **`comfy_gen_info_cache.json`** disk cache — the fallback used when
   SSH is not configured (the mini PC default since 2026-04-XX).
4. **Empty result** + error — UI shows "no LoRAs".

**Design assumptions**:
- The disk cache is populated by **`comfy-gen info`** running on the
  mini PC (triggered by the ComfyGen block's "Sync" button). If the
  CLI is missing or the call fails silently, the cache becomes stale
  and the UI lags reality.
- The cache stores **flat lists** of filenames, not classified groups.
  Family classification happens client-side (kind of — it's done at
  the API layer reading from cache then routing through `classify_lora`).

**Common gotchas**:
- The "Sync" button is hard-disabled when the `comfy-gen` CLI is not
  found on PATH. Users without CLI must populate the cache by other
  means (e.g. a manual RunPod `list_models` call written to disk).
- `comfy-gen` is not on PyPI — installing it requires a local path or
  custom git URL. Do NOT add it to `app.py`'s PEP 723 `dependencies`.

---

## Mobile UI (`/m`)

**Owner files**:
- `frontend/src/app/m/page.tsx` — single-file 3,600+ line monolith
- `backend/m_routes.py` — server-side workflow builders + dispatchers
- `backend/m_store.py` — cost log, presets, batch state

**Source of truth**: the file at `frontend/src/app/m/page.tsx` is the
*entire* mobile UX. No code is shared with `/generate` (the desktop
canvas) except for shared *components* (`InlineLoraPicker`) and
*libraries* (`lora-mapping`, `comfygen-overrides`).

**Dual-Implementation Rule** (CLAUDE.md, MUST FOLLOW):
- Any user-visible UX change made on the desktop side requires a
  corresponding change here.
- Has been forgotten **at least 3 times** historically. Do the
  cross-grep before you commit.

**Design assumptions**:
1. The mobile UI does NOT load ComfyUI workflows. It builds them
   server-side from form inputs via `m_routes.build_*_workflow`.
2. There is no "block graph" model on mobile — it is a tabbed flat
   form. The "ModelKind" enum (`illustrious | z_image | wan_i2v |
   wan_animate`) drives which form sections render.
3. Mobile prompts are first-class form fields (positive + negative both
   always visible) — this is the UX the desktop side will move toward
   per ADR 0002.

**Common gotchas**:
- Adding a new model: requires changes in `page.tsx` *and*
  `m_routes.py` (builder + dispatcher) *and* `m_store.py`
  (`_VIDEO_MODELS` if applicable, `COST_RATES` if billable).
- The monolith is overdue for splitting (planned `m/sections/*.tsx`).
  Until that lands, large diffs to this file are normal — review them
  in chunks.

---

## Pipeline Runtime (frontend)

**Owner files**:
- `frontend/src/lib/pipeline/registry.ts` — block type registration
- `frontend/src/lib/pipeline/pipeline-context.tsx` — execute orchestrator
- `frontend/src/lib/pipeline/serverless-poller.ts` — RunPod status polling
- `custom_blocks/<slug>/frontend.block.tsx` — per-block execute() impls

**Source of truth**: each block's `execute(inputs, signal, helpers)`
async function. The runner walks the chain left-to-right, threading
outputs to inputs by `PortKind`, and propagates an `AbortSignal` for
cancellation.

**Design assumptions**:
1. **Outputs are accumulated by PortKind**, not by block id. A
   `text` output from any upstream block can flow into any downstream
   `text` input.
2. **Cancellation is tab-scoped** — calling stop on tab A does not
   abort jobs spawned by tab B even if both reach the same RunPod
   endpoint.
3. **Iterator blocks** (e.g. ComfyGen Automation, Upload Image multi)
   produce N outputs; the runner re-executes downstream blocks once
   per item.

**Common gotchas**:
- `useSessionState` keys are scoped per `blockId`, not per session.
  Reordering blocks is fine; deleting + re-adding a block at the same
  position will pick up stale state if the new block has the same id
  (rare but happens during dev).

---

## Workflow Builders (`m_routes.py`)

**Owner files**: `backend/m_routes.py` — `build_*_workflow()` family.

**Contract**: each builder takes form-style kwargs (prompt, negative,
width, height, length, fps, base_loras, high_loras, low_loras,
checkpoint, etc.) and returns a fully-formed ComfyUI **API-format**
workflow dict ready to POST to RunPod.

**Design assumptions**:
1. Builders patch a checked-in **template JSON** (e.g.
   `custom_blocks/wan_animate/workflow_template.json`) rather than
   building nodes from scratch. Templates are sources of truth for
   node ids and graph structure.
2. **Well-known node ids** are referenced by string ("10" for the
   positive CLIPTextEncode, "11" for negative, etc.). Changing the
   template's node ids requires updating the builder in lockstep.
3. LoRA injection: high/low LoRAs are appended to a chain starting
   from a known anchor node. Order matters — first picked = closest
   to the model loader.

**Common gotchas**:
- Filename mismatches between the template and the on-disk file
  cause RunPod to fail with "missing model". The 2026-05-03 Wan
  Animate v1/v2 incident is the canonical example.

---

## RunPod Worker Handler

**Owner files** (in the `ai-creator-stack` repo, NOT BlockFlow):
- `docker-comfyui/handler/` — vendored copy of
  [`Hearmeman24/remote-comfy-gen-handler`](https://github.com/Hearmeman24/remote-comfy-gen-handler)
- `docker-comfyui/aria2c-wrapper.sh` — the curl-backed shim installed
  at `/usr/bin/aria2c` to bypass Cloudflare WAF on b2.civitai.com
- `docker-comfyui/Dockerfile` — image build recipe

**Pristineness rule** (2026-05-03):
**Do not edit `docker-comfyui/handler/*.py` directly.** Those files are
verbatim from Hearmeman's upstream repo (md5 ``5223f55c…`` for
`download_handler.py` matches GitHub HEAD as of 2026-05-03). Editing
them in place creates merge friction every time we pull upstream.

If you need to change worker behaviour, do it via:
1. **Docker-level shims** (e.g. the aria2c wrapper) that rename the
   binary and install a script with the same name. The vendored Python
   keeps invoking the binary unchanged.
2. **Dockerfile changes** to add custom nodes, env vars, or
   fix-the-symptom patches at the OS layer.
3. **Forking** with a clear note in `SUBSYSTEMS.md` only if shims aren't
   feasible. Document the divergence here.

**Common gotchas**:
- `--source civitai` path in `download_handler.py` calls
  `/tools/civitai-downloader/download_with_aria.py` which is **not in
  the image**. Callers must use `source="url"` with a civitai API URL.
  Tracked in `docs/runpod_worker_civitai_dl_bug.md`.

---

## Worker Image / Dockerfile

**Tag scheme**: `satoso2/comfyui-serverless:vNN-<reason>` —
`v9-delete`, `v10-civitai-ua`, `v11-curl-wrapper`, etc. `:latest` is
also pushed and tracks the most recent stable.

**Build / push / recycle flow**:
1. Edit under `docker-comfyui/`
2. `cd docker-comfyui && docker build -t satoso2/comfyui-serverless:vNN-<reason> -t :latest .`
3. `docker push satoso2/comfyui-serverless:vNN-<reason>`
4. RunPod GraphQL `saveTemplate` mutation to point template
   `v9c2a1fehv` → new tag (image name only, all other env preserved)
5. RunPod GraphQL `saveEndpoint` to set `workersMax: 0` then
   `workersMax: 3` to drain + restart workers. `workersMin: 0` stays.
6. End-to-end test: `dl_onepiece_loras.py --execute` for civitai-touching
   changes; arbitrary download for HuggingFace-only changes.

**Cost**: rebuild + push is free. Worker recycle drains live workers
which costs nothing if idle. Test downloads are typically < $0.20.

**Common gotchas**:
- Docker layer cache makes most rebuilds <1 min after the first build.
  If you change PyTorch / CUDA base, expect 15-30 min and ~6 GB of
  download bandwidth.
- `:latest` tag must be pushed too — RunPod templates pinned to
  `:latest` won't pick up a new digest until you also push under that
  tag.

---

## Network volume layout

The RunPod endpoint mounts a 200 GB persistent network volume at
`/runpod-volume/`. Layout:

```
/runpod-volume/ComfyUI/models/
  checkpoints/        SDXL Illustrious, LTX, etc.
  diffusion_models/   Z-Image, Wan 2.2 (i2v / fun_control / animate)
  loras/              All LoRAs, family-mixed
  text_encoders/      qwen_3_4b, umt5, t5xxl
  vae/                wan_2.1_vae, sdxl_vae, etc.
  clip_vision/        clip_vision_h
  upscale_models/     4x_foolhardy_Remacri, etc.
  controlnet/         diffusers_xl_canny_full
```

**Family → ckpt_dir mapping** is encoded in
`backend/base_models.py::BaseModelFamily.ckpt_dir`. The download
handler routes `dest` keys to the corresponding subdirectory.

**Don't** put LoRAs in `diffusion_models/` "to keep things together" —
ComfyUI's loader looks specifically in `loras/`.

---

## R2 / tmpfiles storage

**tmpfiles.org** is the bridge for sending local images / videos to
RunPod. Files go up via `backend/tmpfiles.py`, get a 1-hour TTL URL,
and are referenced in the workflow JSON by URL.

**R2** (Cloudflare) is the persistent gallery store. Generation
outputs that should survive past 1 hour are uploaded by the worker's
`storage.py` to the R2 bucket configured via the `COMFY_GEN_S3_*` env
vars in the RunPod template.

**Gotcha**: R2 URLs in `gallery_urls.md` have a 7-day signed-URL TTL.
Refresh via `workflows/refresh_urls.py` (in `ai-creator-stack` repo).

---

## Wan Animate scaffolding

**Owner files**:
- `custom_blocks/wan_animate/` — desktop block + canvas template +
  workflow_template.json + design doc (`WAN_ANIMATE_DESIGN.md`)
- `backend/m_routes.py::build_wan_animate_workflow` — mobile builder

**Status (2026-05-03)**: scaffolded by Web Claude in commits
`890626d`, `b743302`, etc. **Not smoke-tested end-to-end on RunPod**.

**Known issue**: `workflow_template.json` references
`Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors` (v1, on-disk
filename used to point at this when `b743302` landed). On 2026-05-03
desktop Claude deleted this file and downloaded the v2 variant
(`..._scaled_e4m3fn_KJ_v2.safetensors`) believing v2 was correct for
native ComfyUI. The block now points at a missing file.

**Resolution options** (pending user decision):
- Re-download v1 (~17 GB, ~$0.10) and keep template as is.
- Update template to v2 filename (commit only, no DL). Confirm with
  Kijai's wrapper README that v2 also works in WanVideoWrapper.
- Combination: keep v2, document v1 as a deprecated alternative for
  wrapper-strict users.

**Don't** invoke the Wan Animate block until this is resolved — the
RunPod call will fail with a missing-model error.

---

## How to add a new section

When you build a new subsystem (or formalize an existing one), append a
section here using this skeleton:

```
## <Subsystem name>

**Owner files**: <list>

**Source of truth**: <one-paragraph statement>

**Design assumptions**:
1. ...
2. ...

**Common gotchas**:
- ...

**DO NOT** ... without escalation.

**Safe extension path**: ...
```

Update the table of contents at the top.
