# ADR 0001: Prompt UI is workflow-driven (CLIPTextEncode → textareas)

- **Status**: Superseded by [ADR 0002](0002-always-on-prompt-fields.md) (2026-05-03)
- **Date**: ~2026-02 (original) / 2026-05-03 (audit)
- **Authors**: original author unknown (pre-Pre-Task-Charter era);
  audit by Desktop Claude on 2026-05-03

## Context

ComfyUI workflows have widely varying prompt structure:

- A vanilla SDXL Illustrious workflow has 1 positive + 1 negative
  `CLIPTextEncode` node = 2 prompts
- A Wan 2.2 I2V 2-pass workflow can have 4 prompts (high-noise +
  low-noise pairs) or share a single positive across passes
- Prompt-traveling workflows have N prompts, one per latent step
- Some workflows have no negative prompt at all (Z-Image works best
  with empty negative)

The desktop ComfyGen block needs UI controls that match the loaded
workflow's prompt slots, in arbitrary count.

## Decision

The ComfyGen frontend block parses the uploaded workflow JSON via
`/api/blocks/comfy_gen/parse-workflow` and receives an array of
detected text nodes (`text_overrides`). For each detected node, the UI
renders one `<Textarea>` whose value is sent back at run time as a
workflow override.

Implementation:
- Detection in `custom_blocks/comfy_gen/backend.block.py::_detect_text_overrides`
- Render in `custom_blocks/comfy_gen/frontend.block.tsx` lines ~2084-2200
- The `is_negative` heuristic (CLIPTextEncode output flowing into a
  KSampler `negative` input) tags overrides for the `showNegativePrompts`
  toggle introduced in commit `f6c170e`

## Consequences

- ✅ Workflows with custom prompt structure (4-prompt 2-pass, prompt
  traveling, etc.) work without UI changes — the block adapts.
- ✅ Each prompt's underlying node id is preserved, so override
  injection at run time is unambiguous.
- ⚠️ The user must "load a workflow first, then write prompts". This
  inverts the natural mental model where the prompt is the primary
  input and the workflow is implementation detail.
- ❌ **0 detected text nodes → 0 textareas rendered** (the current
  failure mode). Users see no prompt UI and don't know where to type.
  Causes:
  - Workflow parse error (e.g. user uploaded UI/graph format instead of
    API format) — error is shown inline but easy to miss
  - Workflow legitimately has no `CLIPTextEncode` (rare)
  - Workflow uses a non-standard prompt-encoding class the parser
    doesn't recognize
- ❌ **All-negative parse + toggle off** also yields 0 visible textareas,
  for the same reason.

## Why this is being superseded

The 2026-05-03 user-reported issue: "ブロック削除して新規作成しても prompt 欄が出てこない".
Even with the fully-featured `illustrious_base.json` (which parses
correctly to 5 LoRA + 2 prompts on the maintainer's machine), the
mini PC instance was rendering 0 textareas. Whatever the proximate
cause (different file, parser regression, frontend state corruption),
the user's UX expectation is reasonable and the current design's
"silent prompt UI absence" is the root failure mode.

[ADR 0002](0002-always-on-prompt-fields.md) replaces this approach with
an always-on prompt UI that uses workflow detection as **fallback /
suggestion** rather than as **the source of UI shape**.

## Alternatives considered (and rejected at the time)

- **Static positive + negative textareas, ignore detection** — too
  rigid for 2-pass / prompt-traveling workflows.
- **Hybrid (static fallback + per-node advanced editor)** — what
  ADR 0002 finally adopts. Rejected originally for implementation
  cost; cost is now justified by recurring user friction.
