# ADR 0002: Always-on prompt fields with workflow detection as fallback

- **Status**: Proposed (2026-05-03)
- **Date**: 2026-05-03
- **Authors**: Desktop Claude + user discussion
- **Supersedes**: [ADR 0001](0001-workflow-driven-prompt-ui.md)

## Context

Per the analysis in ADR 0001, the workflow-driven prompt UI silently
fails when the parser detects 0 text nodes. The user has hit this
recurringly and asked for a root-cause fix rather than yet another
patch.

The user's mental model: **"I want to write a prompt and generate. The
workflow is implementation detail; it should never make my prompt input
disappear."**

## Decision

The ComfyGen block will always render at least:
- 1 positive prompt textarea (always visible)
- 1 negative prompt textarea (always visible by default; the existing
  `showNegativePrompts` toggle becomes "Show advanced per-node
  controls" instead)

When the loaded workflow's `text_overrides` array is non-empty, those
detected entries populate the textareas (one positive, one negative,
chosen by `is_negative` flag) **as initial values / placeholders**, and
extra detected entries (3rd, 4th prompt for multi-pass workflows) are
exposed in an "Advanced — Per-node prompts" collapsible section.

Run-time behaviour:

- If `text_overrides[]` is non-empty: use detected node ids for
  override injection as today.
- If `text_overrides[]` is empty: inject the positive textarea text
  into the *first detected* `CLIPTextEncode` node's `text` input
  (heuristic), or, if no CLIPTextEncode at all, surface a clearer
  error than "blank UI".

## Consequences

- ✅ Users always see a prompt input regardless of workflow state.
- ✅ Existing 2-pass / prompt-traveling workflows still work — their
  extra prompts move to the Advanced section but remain editable.
- ✅ Loading a fresh workflow no longer feels like "did I break it?".
- ⚠️ Implementation requires changes in
  `custom_blocks/comfy_gen/frontend.block.tsx` (render logic + state
  initialization) and `custom_blocks/comfy_gen/backend.block.py`
  (run-time injection fallback when no nodes were detected).
- ⚠️ Existing user session state has the
  `block_<id>_show_negative_prompts` key. Migration: keep the key and
  rename the rendered label; old "off" state means "advanced section
  collapsed". No data loss.
- ❌ Slight cost: the always-on textareas take vertical space even
  when empty. The Advanced collapsible mitigates this for power-user
  multi-prompt workflows.

## Implementation plan

1. **Compute** an `effectiveTextOverrides` shape: at minimum
   `{positive: <node_id|null>, negative: <node_id|null>, extras: [...]}`
   derived from `text_overrides`. If detection returned 0 entries,
   `positive` and `negative` are `null` but the textareas still render.
2. **Render** positive + negative textareas at the top of the prompt
   section unconditionally. Wire their values to existing
   `textValues` state under synthetic keys when no node id exists.
3. **Run-time** override builder: if `positive.node_id` is set, inject
   into that node's `text` input; otherwise patch the *first*
   CLIPTextEncode in the workflow as a fallback. Same for negative.
4. **Advanced section**: collapsible, holds the extras (`text_overrides`
   beyond the first positive + first negative).
5. **Migration**: `showNegativePrompts` flag → repurpose as
   `showAdvancedPrompts`. Default off.
6. **Test**: parity test in pytest that the override builder produces
   the same workflow output for a `text_overrides[]` non-empty input
   as before.

## Alternatives considered

- **Keep ADR 0001, improve the empty-case error message** — just
  papers over the symptom. The user has rejected this.
- **Always-on but no per-node advanced section** — would break power
  users who depend on multi-prompt workflows. Rejected.
- **Always-on AND ditch detection entirely** — loses the run-time
  override flexibility. Rejected.

## Open questions

- Should the negative textarea also be always-visible, or behind the
  toggle (current default off)? **Tentative answer**: always-visible.
  The 2026-05-03 user pushback was as much about negative prompts as
  positive.
- Mobile UI (`/m`) already has always-on positive + negative form
  fields (per `m/page.tsx`). This ADR brings desktop in line with
  mobile, simplifying the dual-implementation maintenance story.
