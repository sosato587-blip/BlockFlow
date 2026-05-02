"""Convert a ComfyUI canvas-format workflow JSON to API format.

The canvas format is what ComfyUI's editor saves. The API format is what
the worker handler (and BlockFlow's RunPod dispatcher) expects: a flat
``{node_id: {class_type, inputs: {...}}}`` dict.

This converter is purpose-built for Kijai's
``wanvideo_WanAnimate_example_01.json`` (66 nodes, ~26 unique classes).
It reads INPUT_TYPES from local copies of the relevant custom-node
source files to map widget values (positional in the canvas) to named
inputs (keyed in the API), and it resolves SetNode / GetNode / Reroute
canvas-helper chains so the API output references real source nodes.

Usage::

    python3 scripts/convert_canvas_to_api.py \
        custom_blocks/wan_animate/workflow_canvas.json \
        custom_blocks/wan_animate/workflow_template.json

The script is also runnable as a one-shot via ``uv run``.

The widget-input mapping is derived from these files (fetched on the
sandbox into /tmp by the previous interactive setup; the script
references them by environment variables so a future run on the
mini PC can point at fresh checkouts):

    WAN_NODES_DIR    -> Kijai/ComfyUI-WanVideoWrapper checkout
    KJ_NODES_DIR     -> Kijai/ComfyUI-KJNodes checkout
    VHS_NODES_DIR    -> Kosinkadink/ComfyUI-VideoHelperSuite checkout
    DWPOSE_NODE_FILE -> Fannovel16/comfyui_controlnet_aux node_wrappers/dwpose.py
    SAM2_NODE_FILE   -> Kijai/ComfyUI-segment-anything-2/nodes.py
    COMFY_CORE_FILE  -> comfyanonymous/ComfyUI/nodes.py

If a needed class isn't found, the script writes its widget values
verbatim under ``_unmapped_widgets_<class_type>`` so a human can patch
them up. That's intentionally noisy — it surfaces missing INPUT_TYPES
rather than silently dropping widget defaults.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Field types that are link-only (NEVER widgets in the canvas). Anything
# else is treated as a widget by default. This is a heuristic; some
# nodes promote scalars to inputs via "convert to widget input" and
# vice versa — the canvas's ``inputs[]`` array is the runtime truth
# for which sockets are linked.
LINK_ONLY_TYPES = frozenset({
    "IMAGE", "MASK", "LATENT", "MODEL", "CLIP", "VAE", "CLIP_VISION",
    "CONDITIONING", "CONTROL_NET", "SAMPLER", "SIGMAS", "GUIDER", "NOISE",
    "AUDIO", "STRING_LIST", "FLOAT_LIST",
    # Kijai
    "WANVIDEOMODEL", "WANVAE", "WANVIDIMAGE_EMBEDS", "WANVIDIMAGE_CLIPEMBEDS",
    "WANVIDEOTEXTEMBEDS", "WANVIDLORA", "WANCOMPILEARGS", "BLOCKSWAPARGS",
    "WANVIDCONTEXT", "VRAM_MANAGEMENTARGS", "VACEPATH", "SELECTEDBLOCKS",
    "SLGARGS", "LOOPARGS", "EXPERIMENTALARGS", "FETAARGS", "CACHEARGS",
    "FLOWEDITARGS", "MULTITALKARGS", "UNI3C_ARGS", "FREEINITARGS",
    "WANVIDEOPROMPTEXTENDER_ARGS", "FANTASYTALKINGMODEL", "MULTITALKMODEL",
    "FANTASYPORTRAITMODEL", "FANTASYTALKING_EMBEDS", "MULTITALK_EMBEDS",
    "UNIANIMATE_POSE", "UNI3C_EMBEDS",
    # SAM2
    "SAM2MODEL", "SAM_MODEL",
    # KJNodes
    "POINTS", "BBOX", "MASK_LIST",
    # VHS
    "VHS_BatchManager", "META_BATCH",
    # Pose
    "POSE_KEYPOINT",
})

# Helper / virtual node types that don't make it into the API output.
HELPER_TYPES = frozenset({
    "Note", "MarkdownNote", "Reroute",
    "GetNode", "SetNode",
    "INTConstant", "FloatConstant", "BooleanConstant", "StringConstant",
    "PrimitiveNode", "PrimitiveStringMultiline", "PrimitiveString",
})

# Manual fallback widget orderings for nodes whose INPUT_TYPES are
# either unparseable by the regex or live in files we don't have.
# Keys are class_type; values are the ordered widget input names.
MANUAL_OVERRIDES: dict[str, list[str]] = {
    # ComfyUI core
    "LoadImage": ["image", "upload"],
    "CLIPVisionLoader": ["clip_name"],
    # Kijai WanVideoWrapper (auto-extractor's depth tracking gets confused
    # by function-call values like ``folder_paths.get_filename_list(...)``
    # so we pin every WanVideo* widget order by hand to avoid silent drops).
    "WanVideoModelLoader": [
        "model", "base_precision", "quantization", "load_device",
        "attention_mode", "rms_norm_function",
    ],
    "WanVideoVAELoader": ["model_name", "precision", "use_cpu_cache", "verbose"],
    "WanVideoTextEncodeCached": [
        "model_name", "precision", "positive_prompt", "negative_prompt",
        "quantization", "use_disk_cache", "device",
    ],
    "WanVideoClipVisionEncode": [
        "strength_1", "strength_2", "crop", "combine_embeds",
        "force_offload", "tiles", "ratio",
    ],
    "WanVideoAnimateEmbeds": [
        "width", "height", "num_frames", "force_offload",
        "frame_window_size", "colormatch", "pose_strength",
        "face_strength", "tiled_vae",
    ],
    "WanVideoSampler": [
        # ComfyUI auto-injects ``control_after_generate`` as a hidden
        # widget right after any ``seed`` widget. The canvas saves it
        # as widget index 4 with values like 'fixed' / 'increment' /
        # 'decrement' / 'randomize'. The worker handler accepts and
        # ignores it on API submission.
        "steps", "cfg", "shift", "seed", "control_after_generate",
        "force_offload", "scheduler", "riflex_freq_index",
        "denoise_strength", "batched_cfg",
        "rope_function", "start_step", "end_step", "add_noise_to_samples",
    ],
    "WanVideoDecode": [
        "enable_vae_tiling", "tile_x", "tile_y",
        "tile_stride_x", "tile_stride_y", "normalization",
    ],
    "WanVideoBlockSwap": [
        "blocks_to_swap", "offload_img_emb", "offload_txt_emb",
        "use_non_blocking", "vace_blocks_to_swap",
        "prefetch_blocks", "block_swap_debug",
    ],
    "WanVideoTorchCompileSettings": [
        "backend", "fullgraph", "mode", "dynamic",
        "dynamo_cache_size_limit", "compile_transformer_blocks_only",
        "dynamo_recompile_limit", "force_parameter_static_shapes",
        "allow_unmerged_lora_compile",
    ],
    "WanVideoContextOptions": [
        "context_schedule", "context_frames", "context_stride",
        "context_overlap", "freenoise", "verbose", "fuse_method",
    ],
    "WanVideoLoraSelectMulti": [
        "lora_0", "strength_0", "lora_1", "strength_1",
        "lora_2", "strength_2", "lora_3", "strength_3",
        "lora_4", "strength_4", "low_mem_load", "merge_loras",
    ],
    "WanVideoSetBlockSwap": [],
    "WanVideoSetLoRAs": [],
    # KJNodes
    "GetImageSizeAndCount": [],
    "ImageResizeKJv2": [
        "width", "height", "upscale_method", "keep_proportion",
        "pad_color", "crop_position", "divisible_by", "device",
    ],
    "ImageConcatMulti": ["inputcount", "direction", "match_image_size"],
    "ImageCropByMaskAndResize": [
        "base_resolution", "padding", "min_frames", "max_frames", "mask_blur",
    ],
    "PixelPerfectResolution": ["resize_mode"],
    "PointsEditor": [
        "points_store", "coordinates", "neg_coordinates", "bbox_store",
        "bboxes", "width", "height",
    ],
    "BlockifyMask": ["block_size"],
    "GrowMask": ["expand", "tapered_corners"],
    "DrawMaskOnImage": ["color", "alpha"],
    "FaceMaskFromPoseKeypoints": ["person_index"],
    # VHS
    "VHS_LoadVideo": [
        "video", "force_rate", "custom_width", "custom_height",
        "frame_load_cap", "skip_first_frames", "select_every_nth", "format",
    ],
    "VHS_VideoCombine": [
        "frame_rate", "loop_count", "filename_prefix", "format",
        "pix_fmt", "crf", "save_metadata", "trim_to_audio", "pingpong", "save_output",
    ],
    # ControlNet aux
    "DWPreprocessor": [
        "detect_hand", "detect_body", "detect_face",
        "resolution", "bbox_detector", "pose_estimator", "scale_stick_for_xinsr_cn",
    ],
    # SAM2
    "DownloadAndLoadSAM2Model": ["model", "segmentor", "device", "precision"],
    "Sam2Segmentation": ["keep_model_loaded"],
}

# Files to grep for INPUT_TYPES at startup. Order matters only for tie
# breaking when two repos define the same class name (first wins).
def _candidate_source_files() -> list[Path]:
    paths = []
    # Kijai WanVideoWrapper (already on disk)
    for fn in ("wan_nodes.py", "nodes_sampler.py", "nodes_model_loading.py", "nodes_utility.py"):
        p = Path("/tmp") / fn
        if p.exists():
            paths.append(p)
    # The other custom-node sources we fetched into /tmp/ext_*.py
    for p in sorted(Path("/tmp").glob("ext_*.py")):
        paths.append(p)
    # Allow override via env vars for reruns on a different host
    for envname in ("WAN_NODES_FILE", "KJ_NODES_FILE", "VHS_NODES_FILE",
                    "DWPOSE_NODE_FILE", "SAM2_NODE_FILE", "COMFY_CORE_FILE"):
        v = os.environ.get(envname)
        if v and Path(v).exists():
            paths.append(Path(v))
    return paths


# More forgiving INPUT_TYPES parser that handles both the
# ``return {...}`` form and the ``input_types = {...}; return input_types``
# form, and tolerates nested braces.
_CLASS_HEAD_RE = re.compile(r"^class (\w+)(\([^)]*\))?:", re.MULTILINE)
_INPUT_TYPES_RE = re.compile(r"def\s+INPUT_TYPES\s*\(\s*\w*\s*\)\s*:")


def _balanced_brace_slice(text: str, start: int) -> str | None:
    """Return the substring starting at ``text[start] == '{'`` up to the
    matching closing brace (inclusive). None if unbalanced."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = None
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\" and i + 1 < len(text):
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"'):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        i += 1
    return None


def _find_input_types_body(class_block: str) -> str | None:
    """Locate the INPUT_TYPES dict body inside a class definition string."""
    m = _INPUT_TYPES_RE.search(class_block)
    if not m:
        return None
    tail = class_block[m.end():]
    # Try to find the dict literal that's either returned directly or
    # assigned to a local name. We look for the first '{' after the
    # signature and grab the balanced slice; this captures both forms.
    brace_idx = tail.find("{")
    if brace_idx < 0:
        return None
    return _balanced_brace_slice(tail, brace_idx)


def _split_classes(src: str) -> dict[str, str]:
    """Slice a Python source file into ``{class_name: class_body}``."""
    blocks: dict[str, str] = {}
    matches = list(_CLASS_HEAD_RE.finditer(src))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        # Only keep the FIRST occurrence (Kijai sometimes redefines)
        blocks.setdefault(name, src[start:end])
    return blocks


def _extract_widget_field_names(body: str) -> list[str]:
    """From an INPUT_TYPES body, return widget field names in order.

    Walks both ``"required"`` and ``"optional"`` sections, picking the
    fields whose declared type is NOT in ``LINK_ONLY_TYPES``.
    """
    fields: list[str] = []
    for sect in ("required", "optional"):
        sect_re = re.compile(rf'"{sect}"\s*:\s*\{{')
        m = sect_re.search(body)
        if not m:
            continue
        inner = _balanced_brace_slice(body, m.end() - 1)
        if not inner:
            continue
        # Each entry: "<name>": (<TYPE_OR_LIST>, ...)
        # We iterate by scanning for top-level keys at depth 1.
        depth = 0
        in_str = None
        i = 0
        keys: list[tuple[int, str]] = []  # (offset_after_colon, name)
        while i < len(inner):
            ch = inner[i]
            if in_str:
                if ch == "\\" and i + 1 < len(inner):
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ("'", '"'):
                    in_str = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                if depth == 1 and ch == '"':
                    # Possible start of a key. Read until next unescaped '"'.
                    end_q = inner.find('"', i + 1)
                    if end_q < 0:
                        break
                    key_name = inner[i + 1 : end_q]
                    after = inner[end_q + 1 :]
                    if after.lstrip().startswith(":"):
                        # this is a key
                        # Determine the value type: parse what follows ':'
                        colon = inner.find(":", end_q + 1)
                        rest = inner[colon + 1 :].lstrip()
                        # Either ("TYPE", ...) or (["a","b",...], ...)
                        is_link_only = False
                        if rest.startswith("("):
                            after_paren = rest[1:].lstrip()
                            tm = re.match(r'"(\w+)"', after_paren)
                            if tm and tm.group(1) in LINK_ONLY_TYPES:
                                is_link_only = True
                        if not is_link_only:
                            fields.append(key_name)
                        # advance past closing quote so loop continues on next key
                        i = end_q + 1
                        continue
            i += 1
    return fields


def build_widget_map() -> dict[str, list[str]]:
    """Walk all candidate source files and build the class -> widget-fields map."""
    out: dict[str, list[str]] = {}
    for path in _candidate_source_files():
        try:
            src = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for class_name, body in _split_classes(src).items():
            if class_name in out:
                continue  # earlier file wins
            sub = _find_input_types_body(body)
            if not sub:
                continue
            fields = _extract_widget_field_names(sub)
            out[class_name] = fields
    # Manual overrides take precedence (even over auto-detected, in case the
    # auto detect picked up a slightly wrong order).
    out.update(MANUAL_OVERRIDES)
    return out


# ---------------------------------------------------------------------------
# Canvas resolution
# ---------------------------------------------------------------------------


def build_link_table(canvas: dict) -> dict[int, tuple[int, int]]:
    """``link_id -> (src_node_id, src_output_idx)``."""
    out: dict[int, tuple[int, int]] = {}
    for entry in canvas.get("links", []):
        # Newer canvas: list [link_id, src_node, src_output, dst_node, dst_input, type]
        # Older canvas: dict
        if isinstance(entry, list) and len(entry) >= 5:
            link_id, src_node, src_out = entry[0], entry[1], entry[2]
            out[int(link_id)] = (int(src_node), int(src_out))
        elif isinstance(entry, dict):
            out[int(entry["id"])] = (int(entry["origin_id"]), int(entry["origin_slot"]))
    return out


def build_alias_table(canvas: dict, links: dict[int, tuple[int, int]]) -> dict[str, int]:
    """SetNode/GetNode pair: published-name -> link_id of the SetNode's input."""
    name_to_link: dict[str, int] = {}
    for n in canvas["nodes"]:
        if n["type"] != "SetNode":
            continue
        # Published name lives at widgets_values[0]
        wv = n.get("widgets_values") or []
        if not wv:
            continue
        name = wv[0]
        # SetNode has one input slot whose link is the source
        for inp in n.get("inputs", []):
            if inp.get("link") is not None:
                name_to_link[name] = int(inp["link"])
                break
    return name_to_link


def resolve_link(
    link_id: int,
    canvas_nodes_by_id: dict[int, dict],
    links: dict[int, tuple[int, int]],
    aliases: dict[str, int],
    seen: set[int] | None = None,
) -> tuple[int, int] | None:
    """Resolve a link through Reroute / GetNode chains to a real (node, output_idx).

    ``aliases`` is the SetNode published-name table built upfront.
    """
    if seen is None:
        seen = set()
    if link_id in seen or link_id not in links:
        return None
    seen.add(link_id)

    src_node_id, src_out_idx = links[link_id]
    src_node = canvas_nodes_by_id.get(src_node_id)
    if src_node is None:
        return src_node_id, src_out_idx

    typ = src_node.get("type")
    if typ == "Reroute":
        # Pass-through: find Reroute's own input link, recurse.
        for inp in src_node.get("inputs", []):
            in_link = inp.get("link")
            if in_link is not None:
                return resolve_link(int(in_link), canvas_nodes_by_id, links, aliases, seen)
        return None
    if typ == "GetNode":
        wv = src_node.get("widgets_values") or []
        if not wv:
            return None
        name = wv[0]
        target_link = aliases.get(name)
        if target_link is None:
            return None
        return resolve_link(int(target_link), canvas_nodes_by_id, links, aliases, seen)

    return src_node_id, src_out_idx


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def convert(canvas: dict, widget_map: dict[str, list[str]]) -> dict[str, dict]:
    nodes_by_id = {int(n["id"]): n for n in canvas["nodes"]}
    links = build_link_table(canvas)
    aliases = build_alias_table(canvas, links)

    api: dict[str, dict] = {}
    skipped: dict[str, int] = {}

    for node in canvas["nodes"]:
        class_type = node["type"]
        node_id = str(node["id"])

        if class_type in HELPER_TYPES:
            skipped[class_type] = skipped.get(class_type, 0) + 1
            continue

        api_inputs: dict[str, Any] = {}
        meta = {}
        if isinstance(node.get("title"), str) and node["title"]:
            meta["title"] = node["title"]
        elif node.get("properties", {}).get("Node name for S&R"):
            pass  # keep node ids only

        # 1) Linked inputs from the canvas inputs[] array.
        seen_input_names: set[str] = set()
        for inp in node.get("inputs", []) or []:
            link_id = inp.get("link")
            name = inp.get("name")
            if not name:
                continue
            seen_input_names.add(name)
            if link_id is None:
                # Not connected. May still be a widget that was "converted to input"
                # — in that case we can't get a value, leave it out.
                continue
            resolved = resolve_link(int(link_id), nodes_by_id, links, aliases)
            if resolved is None:
                continue
            src_node_id, src_out_idx = resolved
            api_inputs[name] = [str(src_node_id), int(src_out_idx)]

        # 2) Widget values mapped to widget field names.
        wv = node.get("widgets_values")
        widget_names = widget_map.get(class_type)
        if widget_names is None:
            if wv:
                # Surface the gap clearly so a human can patch it up.
                api_inputs[f"_unmapped_widgets_{class_type}"] = wv
        elif isinstance(wv, dict):
            # VHS-style dict: copy by key, drop UI-only fields not in widget_names.
            allowed = set(widget_names)
            for k, v in wv.items():
                if k in allowed and k not in seen_input_names:
                    api_inputs[k] = v
        elif isinstance(wv, list):
            for idx, val in enumerate(wv):
                if idx >= len(widget_names):
                    break
                name = widget_names[idx]
                # Skip if this name is already covered by a link in inputs[]
                if name in seen_input_names and name in api_inputs:
                    continue
                api_inputs[name] = val

        api_entry: dict[str, Any] = {"class_type": class_type, "inputs": api_inputs}
        if meta:
            api_entry["_meta"] = meta
        api[node_id] = api_entry

    if skipped:
        print(f"  [convert] skipped helpers: {dict(skipped)}", file=sys.stderr)
    return api


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("canvas", help="Path to canvas-format JSON")
    ap.add_argument("output", help="Path to write API-format JSON")
    args = ap.parse_args()

    canvas = json.loads(Path(args.canvas).read_text(encoding="utf-8"))
    widget_map = build_widget_map()
    print(f"  [convert] widget map: {len(widget_map)} class types loaded", file=sys.stderr)

    api = convert(canvas, widget_map)
    Path(args.output).write_text(
        json.dumps(api, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Quick stats
    unmapped = sum(
        1
        for entry in api.values()
        for k in entry["inputs"]
        if k.startswith("_unmapped_widgets_")
    )
    print(
        f"  [convert] wrote {len(api)} API nodes -> {args.output}"
        f" ({unmapped} nodes had unmapped widget classes)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
