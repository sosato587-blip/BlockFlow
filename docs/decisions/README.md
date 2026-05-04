# Architecture Decision Records (ADRs)

This directory captures **why** the codebase looks the way it does for
non-obvious design choices.

When you make a non-trivial design decision (or revisit one), write an
ADR. Future Claude sessions and humans should be able to read the ADR
and answer "why didn't they just do X?" without spelunking git history.

## Format

Each ADR is a numbered markdown file: `NNNN-short-slug.md`. Use this
template:

```markdown
# ADR NNNN: <decision-in-one-sentence>

- **Status**: Proposed | Accepted | Superseded by ADR NNNN | Deprecated
- **Date**: YYYY-MM-DD
- **Authors**: Claude (instance flavor) / human handle

## Context

What problem are we solving? What constraints exist?

## Decision

The choice we made. One or two paragraphs.

## Consequences

- ✅ Good thing 1
- ✅ Good thing 2
- ⚠️ Trade-off 1
- ❌ Cost 1

## Alternatives considered

What we rejected and why.
```

## Status meanings

- **Proposed** — under discussion, not yet implemented
- **Accepted** — current truth, code reflects this
- **Superseded by ADR NNNN** — replaced by a newer decision; keep the
  file for historical context, but link forward
- **Deprecated** — no longer applies, but kept for reference

## Index

| ADR | Status | Topic |
|---|---|---|
| [0001](0001-workflow-driven-prompt-ui.md) | Superseded by 0002 | Prompt UI is workflow-driven (CLIPTextEncode → textareas) |
| [0002](0002-always-on-prompt-fields.md) | Proposed | Always-on prompt fields with workflow-detected nodes as fallback |
