# BlockFlow Generate Tab — UX Audit (2026-04-21)

## Executive Summary

The Generate tab contains **15 custom blocks** (civitai_share, comfy_gen, generation, hitl, i2v_prompt_writer, image_upscale, image_viewer, lora_selector, prompt_writer, upload_image_to_tmpfiles, upscale, video_loader, video_viewer, wan_22_image_to_video, wan_fun_control) with recurring UX inconsistencies: textarea min-height violations (60–80px vs. the 160px project rule), API-key status messaging divergence, silent error catches, missing disabled-state affordances, unexplained slider ranges, and inconsistent loading feedback. **29 findings total — 8 high, 12 medium, 9 low.**

| Block | H | M | L |
|---|---|---|---|
| civitai_share | 0 | 3 | 1 |
| comfy_gen | 2 | 3 | 1 |
| generation | 1 | 4 | 1 |
| hitl | 0 | 3 | 1 |
| i2v_prompt_writer | 3 | 4 | 0 |
| image_upscale | 0 | 3 | 2 |
| image_viewer | 0 | 2 | 2 |
| lora_selector | 0 | 4 | 1 |
| prompt_writer | 2 | 3 | 0 |
| upload_image_to_tmpfiles | 1 | 2 | 1 |
| upscale | 3 | 3 | 0 |
| video_loader | 0 | 2 | 2 |
| video_viewer | 0 | 2 | 2 |
| wan_22_image_to_video | 2 | 4 | 1 |
| wan_fun_control | 1 | 4 | 1 |

---

## Per-block findings

### civitai_share
Purpose: Share generated media to CivitAI with metadata.
- [M] Line 238 — Warning text uses `text-muted-foreground`; should be `text-red-500` to read as an actual error.
- [M] Line 241 — API-key input is plain password field with no show/hide toggle; user can't verify paste.
- [M] Line 287 — `.catch(() => {})` swallows tag-generation failures silently.
- [L] Line 269–294 — Auto-tag button has no spinner during fetch.

File: `custom_blocks/civitai_share/frontend.block.tsx`

### comfy_gen
Purpose: Load ComfyUI workflows, override nodes, iterate axes.
- [H] ~450–700 — Large form without a shared `<FormField>` wrapper; labels and spacing drift per section.
- [H] No centralized error UI; validation failures don't surface to the user.
- [M] Disabled state lacks "load a workflow first" hint when fields are locked.
- [M] Numeric inputs (steps, CFG) lack min/max attrs / range hints.
- [M] ~800–900 — Batch axis order and output-filename rule not documented in the UI.
- [L] Placeholders drift in tone/specificity across inputs.

File: `custom_blocks/comfy_gen/frontend.block.tsx`

### generation
Purpose: Wan 2.2 T2V submission.
- [H] Line 424 — Prompt textarea `min-h-[80px]`; must be `min-h-[160px]` per project rule.
- [M] Line 456–466 — Seed-mode toggle doesn't tell user that "Fixed" needs the seed input.
- [M] Line 469–472 — Disabled seed input in Random mode shows no "auto-generated" hint.
- [M] Line 476–490 — LoRA section unclear whether it auto-applies or needs wiring.
- [M] No progress feedback while RunPod job spins up.
- [L] Line 350–365 — Resolution presets ("Standard"/"High") don't show pixel dimensions.

File: `custom_blocks/generation/frontend.block.tsx`

### hitl
Purpose: Human-in-the-loop gate.
- [M] Line 107 — Copy "Is this step OK?" too casual for a gate action.
- [M] Continue/Stop buttons: no affordance text when disabled.
- [M] No hint on what "Continue" vs. "Stop" passes downstream.
- [L] Button sizes smaller than peers.

File: `custom_blocks/hitl/frontend.block.tsx`

### i2v_prompt_writer
Purpose: Vision LLM generates video prompt from an uploaded image.
- [H] Line 347 — Missing-image warning is yellow; should be red (this blocks execution).
- [H] Line 351–363 — Model list loads with no spinner / loading state.
- [H] Line 401 — System prompt textarea `min-h-[60px]`.
- [H] Line 260–261 — Variant count silently clamped to min=1 on async load with no toast.
- [M] Line 368–378 — temperature/max_tokens ranges unexplained.
- [M] Line 381–405 — System prompt textarea has no role hint or example placeholder.
- [M] Line 418 — "Output Prompt" label + "Generated prompt will appear here…" placeholder redundant.
- [M] Line 341 — Silent clamping of temperature variants.

File: `custom_blocks/i2v_prompt_writer/frontend.block.tsx`

### image_upscale
Purpose: Topaz image upscale.
- [M] Line 360–362 — API-key status badge ambiguous between "saved" / "using .env" / "missing".
- [M] Line 369 — "Select a model" placeholder gives no hint about naming convention.
- [M] Line 444–469 — Face controls appear/disappear abruptly on category change.
- [L] Line 445–468 — `<span>` used where `<Label>` would match other blocks.
- [L] Line 453 — Strength input has `type="string"` but numeric constraints; should be `type="number"`.

File: `custom_blocks/image_upscale/frontend.block.tsx`

### image_viewer
Purpose: Display image outputs.
- [M] No "wire an upstream block" hint when input is empty.
- [M] "Clear" button label cryptic; recommend "Clear all images".
- [L] Selected-thumbnail border color not theme-semantic.
- [L] Image counter `text-[10px]` too small.

File: `custom_blocks/image_viewer/frontend.block.tsx`

### lora_selector
Purpose: LoRA adapter selector with high/low noise sliders.
- [M] Line 169/191 — "High Noise" / "Low Noise" labels have no explanation of what they mean.
- [M] Line 73–74 — Slider max=2 unexplained; typical range is 0.6–1.2.
- [M] Refresh button missing `aria-label`.
- [M] **LoRAs are listed flat/alphabetical; no base-model grouping — user explicitly flagged this as the main pain point.** See "Base-model-first redesign" section below.
- [L] Slider label copy inconsistent with other blocks.

File: `custom_blocks/lora_selector/frontend.block.tsx`

### prompt_writer
Purpose: LLM prompt generation (image or video mode).
- [H] ~400–450 — "Extra User Prompts" section has no add/remove UI.
- [H] ~350–370 — Silent clamping of `fanoutLimits` on async load.
- [M] Image/Video mode toggle lacks clear active state (only text color changes).
- [M] "Generate Ideas" button label vague.
- [M] Temperature and variant sliders lack range hints.

File: `custom_blocks/prompt_writer/frontend.block.tsx`

### upload_image_to_tmpfiles
Purpose: Upload images locally or to tmpfiles.org.
- [H] Line 285–286 — "pipeline will iterate over each" behavior buried in small text; should be a prominent banner.
- [M] Line 229–233 — Mode explanation `text-[10px] text-muted-foreground` — too small.
- [M] Drag-drop zone lacks format hint ("PNG/JPG/WebP").
- [L] Line 290–295 — "Add More"/"Clear All" button row awkward on narrow widths.

File: `custom_blocks/upload_image_to_tmpfiles/frontend.block.tsx`

### upscale
Purpose: Topaz video upscale.
- [H] Line 270–276 — API-key input is plain; no validate / show-hide.
- [H] Line 289–294 — Progress computed but not rendered.
- [H] Disabled execute button has no "select a video first" affordance.
- [M] Line 271–275 — Enhancement/Interpolation/Encoding dropdowns lack tooltip help.
- [M] Line 330 — Mix of "..." and "…".
- [M] Output format options don't show bitrate/codec.

File: `custom_blocks/upscale/frontend.block.tsx`

### video_loader
Purpose: Load a video (local or tmpfiles).
- [M] Line 204–207 — No visual hierarchy between label and description.
- [M] Line 217 — "META" badge not explained.
- [L] Line 209 — "Browse" button may wrap on narrow widths.
- [L] Line 237–239 — Read-only URL field lacks copy button.

File: `custom_blocks/video_loader/frontend.block.tsx`

### video_viewer
Purpose: Display generated videos.
- [M] No upstream wiring hint on empty state.
- [M] "Clear" label cryptic.
- [L] Counter text too small.
- [L] Selected-thumbnail border not theme-semantic.

File: `custom_blocks/video_viewer/frontend.block.tsx`

### wan_22_image_to_video
Purpose: Wan 2.2 I2V.
- [H] Line 420–424 — Prompt textarea `min-h-[80px]`.
- [H] Line 385–401 — Image requirement not prominent; user can click Generate without an image.
- [M] Line 383–390 — No visual feedback when switching between wired-upstream image and local file.
- [M] Line 412–416 — Seed-mode toggle hint missing (same as generation block).
- [M] Line 432–439 — fps/frames defaults unexplained.
- [M] Line 488 — Primary/outline button variant usage drifts from peers.
- [L] LoRA section integration unclear.

File: `custom_blocks/wan_22_image_to_video/frontend.block.tsx`

### wan_fun_control
Purpose: Motion-control video gen.
- [H] Line 74–82 — CFG / shift / steps sliders lack range guidance.
- [M] Line 80 — "Real" vs. "Anime" selection unexplained.
- [M] Line 199–200 — No wiring guidance for upstream video/image inputs.
- [M] Line 92–99 — Priority when both wired and local inputs present is unclear.
- [M] Output naming convention not documented.
- [L] Ellipsis inconsistency.

File: `custom_blocks/wan_fun_control/frontend.block.tsx`

---

## Cross-cutting recommendations

1. **Shared `<FormField>` wrapper** — one component owning label + hint + error row. Replaces ad-hoc `<div>` wrappers in every block.
2. **Disabled-state messaging** — inline "why disabled" text under disabled primary buttons, not tooltip-only.
3. **Textarea min height** — enforce `min-h-[160px]` globally for prompt-class textareas.
4. **No silent catches** — ban `catch(() => {})`; funnel to a block-local `ErrorBanner`.
5. **Loading feedback** — spinner + "Loading…" for any async >500ms.
6. **API-key status** — standardize badge copy across civitai_share, image_upscale, upscale, i2v_prompt_writer ("Configured" / "Using .env" / "Not set").
7. **Ellipsis** — replace `...` with `…` (U+2026) across tsx.
8. **Numeric range hints** — every slider/number input gets a `(min–max)` label.
9. **Copy-to-clipboard** on every read-only URL field.

## Ready-to-commit quick wins (each <5 min on staging)

1. generation.tsx:424 — `min-h-[80px]` → `min-h-[160px]`
2. wan_22_image_to_video.tsx:420–424 — same
3. i2v_prompt_writer.tsx:401 — `min-h-[60px]` → `min-h-[160px]`
4. lora_selector.tsx:157 — add `aria-label="Refresh LoRA list"` on refresh button
5. image_upscale.tsx:453 — `type="string"` → `type="number"`
6. upscale.tsx:330 — replace `...` with `…`
7. video_loader.tsx:237 — add copy-to-clipboard button on URL readonly
8. civitai_share.tsx:238 — `text-muted-foreground` → `text-red-500`
9. i2v_prompt_writer.tsx:347 — yellow → red
10. image_viewer + video_viewer — `Clear` → `Clear all`
11. wan_fun_control.tsx:74–82 — add `(0–20)` / `(0–1)` / `(20–100)` slider hints

---

## Base-model-first LoRA redesign (user request 2026-04-21)

User feedback: 40+ LoRAs sorted alphabetically, no indication of which base model each belongs to. Wants:

1. A **base-model (checkpoint) dropdown** first — selected at the top of the pipeline.
2. LoRA dropdowns then **filtered by the selected base model** — you literally cannot pick a LoRA that doesn't match.
3. Prep for a future where multiple specialized (LoRA-merged) checkpoints exist, not just the single Illustrious default.

Proposal — shipped incrementally; see `feat/base-model-taxonomy` branch plan in AUTONOMOUS_REPORT_NIGHT2.md.
