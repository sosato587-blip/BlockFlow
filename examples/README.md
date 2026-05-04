# BlockFlow example workflows

Reference ComfyUI **API-format** workflow JSONs that BlockFlow's
`/api/blocks/comfy_gen/parse-workflow` can read. Use these as a known-good
starting point — load via the ComfyGen block's "Load JSON" button.

## Files

| File | Purpose | Detected by parser |
|---|---|---|
| `illustrious_base.json` | Single-pass SDXL Illustrious image gen | 5 LoRA loaders, 2 prompts (positive + negative), 1 EmptyLatentImage (1024×1536), 1 KSampler (Euler-style) |

## Why these are bundled

Historically BlockFlow did not ship example workflows, so each user
ended up with whichever `illustrious_base.json` they happened to copy
from somewhere. Subtly broken or non-API-format copies caused the
parser to silently return empty arrays for `lora_nodes`,
`resolution_nodes`, `ksamplers`, etc., which in turn made entire UI
sections vanish from the ComfyGen block — Resolution, KSampler, inline
LoRA picker — without any error message that pointed at the workflow
file as the cause.

These bundled workflows are the canonical reference. If your own
workflow stops triggering UI sections you expect, diff against the
relevant file here.

## Format requirements (for your own workflows)

ComfyUI exports two JSON shapes:

- **API format** (this is what BlockFlow expects). Top-level dict keyed
  by node id, each value has `class_type` + `inputs`. Export from
  ComfyUI by enabling Dev Mode in settings, then choosing
  "Save (API Format)".
- **UI / graph format**. Top-level has `nodes: [...]`, `links: [...]`,
  `last_node_id`, etc. **BlockFlow rejects this** with a 400 error
  containing the message *"This workflow is in ComfyUI graph format,
  not API format."* Re-export from ComfyUI in API format.

## Updating these examples when models change

If the on-disk model files change (e.g. v17 supersedes v16, see
`docs/decisions/`), update the `ckpt_name` and `lora_name` fields here
so loading still works. Don't add new model dependencies without
checking `backend/base_models.py` for the canonical filename.
