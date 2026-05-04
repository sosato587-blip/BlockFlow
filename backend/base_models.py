"""Base-model taxonomy for checkpoints and LoRAs.

A "base model family" is the architecture a checkpoint / LoRA is tied to:
illustrious (SDXL-anime), z_image (Alibaba S3-DiT), wan_22 (14B video), ltx.

This module exists so the Generate-tab LoRA dropdowns can be filtered by
the selected base model — preventing the classic "I loaded a Wan LoRA
under an Illustrious checkpoint and got garbage" failure mode.

Design notes:
- Classification is filename-pattern-based. No network calls.
- Each family has a display label + which ComfyUI model-type slot it
  loads into (checkpoints / diffusion_models / etc.) — useful for the
  future Base Model Selector block that will also emit workflow overrides.
- LoRAs whose filename matches no family pattern are silently dropped
  from the filtered UI (they can still be selected via the raw dropdown
  in lora_selector's "all" view). Prefer explicit hints like
  `_IllustriousXL` / `_z_image` / `_wan22` / `_ltx` in LoRA filenames.
- `sdxl` / `flux` / `unknown` families were removed (2026-04-22): we only
  keep families with at least one registered checkpoint. Re-add by
  inserting a FAMILIES entry + at least one KNOWN_CHECKPOINTS row.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Families
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseModelFamily:
    id: str
    label: str
    description: str
    # Where the checkpoint file lives in ComfyUI's model directory.
    ckpt_dir: str  # "checkpoints" | "diffusion_models"
    # Ordered for display in dropdowns.
    sort_order: int = 100


FAMILIES: dict[str, BaseModelFamily] = {
    "illustrious": BaseModelFamily(
        id="illustrious",
        label="Illustrious XL",
        description="Anime-styled SDXL derivative. Best for 2D anime / illustration.",
        ckpt_dir="checkpoints",
        sort_order=10,
    ),
    "z_image": BaseModelFamily(
        id="z_image",
        label="Z-Image Turbo",
        description="Alibaba S3-DiT realistic model. Use CLIPLoader + qwen_3_4b + type:lumina2.",
        ckpt_dir="diffusion_models",
        sort_order=30,
    ),
    "wan_22": BaseModelFamily(
        id="wan_22",
        label="Wan 2.2",
        description="14B video diffusion (I2V / Fun Control). Uses wan_2.1_vae.",
        ckpt_dir="diffusion_models",
        sort_order=40,
    ),
    "ltx": BaseModelFamily(
        id="ltx",
        label="LTX Video",
        description="Lightricks LTX 2B video model. ~4-6× cheaper than Wan.",
        ckpt_dir="diffusion_models",
        sort_order=60,
    ),
}


# ---------------------------------------------------------------------------
# Known checkpoints (manually curated; extend as new models land on RunPod)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckpointInfo:
    filename: str
    family: str
    label: str
    notes: str = ""
    # If non-empty, this is a LoRA-merged checkpoint specialized for a use case.
    merged_loras: tuple[str, ...] = field(default_factory=tuple)


KNOWN_CHECKPOINTS: list[CheckpointInfo] = [
    CheckpointInfo(
        filename="waiIllustriousSDXL_v170.safetensors",
        family="illustrious",
        label="WAI Illustrious XL v1.7.0",
        notes=(
            "Main anime checkpoint. 6.6GB, SDXL arch. v17.0 over v16.0: "
            "background-character color/relevance fixes, smoother coloring, "
            "and notably better Hires-fix limb correction (arms/legs/hands). "
            "Lower step count works (recommended 15-30 vs 25-40 in v16), "
            "so per-image RunPod cost drops. Default character age tends "
            "younger; for adult-look without a character LoRA, prepend "
            "(aged up:1.0-2.0) or (mature female:1.0-2.0) to the prompt. "
            "All Illustrious LoRAs trained against v16 still work unchanged. "
            "Source: https://civitai.com/models/827184 (modelVersionId=2883731)."
        ),
    ),
    CheckpointInfo(
        filename="nova3DCGXL_illustriousV90.safetensors",
        family="illustrious",
        label="Nova 3DCG XL v9.0",
        notes=(
            "3DCG / PVC-figure-style anime checkpoint. ~6.5GB, SDXL arch. "
            "Built on NoobAI EPS v1.1 + Illustrious v2.0-stable (DARE merge). "
            "Compatible with Illustrious LoRAs. "
            "Source: https://civitai.com/models/715287 (modelVersionId=2744564). "
            "If the downloaded file uses a different filename (civitai keeps "
            "the uploader's name), rename it to the value above or update "
            "this row."
        ),
    ),
    CheckpointInfo(
        filename="z_image_turbo_bf16.safetensors",
        family="z_image",
        label="Z-Image Turbo (bf16)",
        notes="Realistic. 11.7GB. Needs qwen_3_4b + type:lumina2.",
    ),
    CheckpointInfo(
        filename="wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        family="wan_22",
        label="Wan 2.2 I2V high-noise 14B (fp8)",
        notes="High-noise half of the 2-pass Wan I2V workflow.",
    ),
    CheckpointInfo(
        filename="wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        family="wan_22",
        label="Wan 2.2 I2V low-noise 14B (fp8)",
        notes="Low-noise half of the 2-pass Wan I2V workflow.",
    ),
    CheckpointInfo(
        filename="wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors",
        family="wan_22",
        label="Wan 2.2 Fun Control high-noise 14B (fp8)",
        notes="High-noise half for pose-controlled video.",
    ),
    CheckpointInfo(
        filename="wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors",
        family="wan_22",
        label="Wan 2.2 Fun Control low-noise 14B (fp8)",
        notes="Low-noise half for pose-controlled video.",
    ),
    CheckpointInfo(
        filename="Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors",
        family="wan_22",
        label="Wan 2.2 Animate 14B (fp8 KJ)",
        notes=(
            "Single-pass character-animation model: reference image + "
            "driving video -> animated character. ~17 GB. The Kijai "
            "WanVideoWrapper example workflow expects this exact filename "
            "(see custom_blocks/wan_animate/WAN_ANIMATE_DESIGN.md for the "
            "full required-files list and node graph). "
            "Source: https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled "
            "(path: WanVideo/2_2/). bf16 alt: wan2.2_animate_14B_bf16.safetensors "
            "(~28 GB, Comfy-Org/Wan_2.2_ComfyUI_Repackaged) — uses a different, "
            "simpler workflow (WanAnimateToVideoEnhanced) and is NOT what the "
            "current scaffolding targets."
        ),
    ),
    CheckpointInfo(
        filename="WanAnimate_relight_lora_fp16.safetensors",
        family="wan_22",
        label="Wan Animate relight LoRA (fp16)",
        notes=(
            "Relight LoRA recommended by Kijai's example workflow. "
            "Default strength 1.0. ~600 MB. "
            "Source: https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled "
            "(path: WanVideo/)."
        ),
    ),
    CheckpointInfo(
        filename="lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
        family="wan_22",
        label="lightx2v I2V 14B 480p CFG step-distill rank64 (bf16)",
        notes=(
            "Speed-distillation LoRA. Lets Wan 2.2 Animate run at "
            "steps=6 instead of 25-30 with negligible quality loss; "
            "default strength 1.2. ~1 GB. "
            "Source: https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled "
            "(path: WanVideo/Lightx2v/)."
        ),
    ),
    CheckpointInfo(
        filename="ltx-video-2b-v0.9.5.safetensors",
        family="ltx",
        label="LTX Video 2B v0.9.5",
        notes="Fast/cheap video. Needs t5xxl text encoder.",
    ),
]


def known_checkpoints_by_family() -> dict[str, list[CheckpointInfo]]:
    """Group the curated checkpoint list by family."""
    out: dict[str, list[CheckpointInfo]] = {}
    for cp in KNOWN_CHECKPOINTS:
        out.setdefault(cp.family, []).append(cp)
    return out


# ---------------------------------------------------------------------------
# LoRA classifier
# ---------------------------------------------------------------------------

# Explicit overrides for LoRAs whose filenames lack architecture hints.
# Key is the lowercased base filename (without directory). Value is a family id.
# Keep this list short — prefer renaming the LoRA to include an architecture
# hint when possible, or broadening _LORA_PATTERNS below if a pattern is
# generalisable. This map exists for historical names we can't rename and
# for one-off filenames the regex would not safely catch.
_LORA_OVERRIDES: dict[str, str] = {
    # Illustrious NSFW utility/concept LoRAs (used in sexy_12 / nami batches)
    "smooth_detailer_booster.safetensors": "illustrious",
    "aesthetic_quality_masterpiece.safetensors": "illustrious",
    "mating_press_side_concept.safetensors": "illustrious",
    "fellatio_couch_concept.safetensors": "illustrious",
    "penis_over_one_eye_concept.safetensors": "illustrious",
    "shiny_nai_style.safetensors": "illustrious",
    "straddling_kiss_concept.safetensors": "illustrious",
    # Z-Image realistic-style LoRAs
    "nicegirls_ultrareal.safetensors": "z_image",
    "realistic_skin_texture.safetensors": "z_image",
    # 2026-05-03: One Piece character set whose filenames lack any
    # architecture marker the regex can grab on to.
    "boa_hancock.safetensors": "illustrious",
    "nicorobin_onepiece[nyx].safetensors": "illustrious",
    "one_piece_manga_style.safetensors": "illustrious",
    # 2026-05-03: Generic-named Illustrious concept / style / quality LoRAs
    # that the user confirmed are SDXL Illustrious.
    "hotspring.safetensors": "illustrious",
    "kodak film style v1.safetensors": "illustrious",
    "schoolgirl.safetensors": "illustrious",
    "smooth_booster_v4.safetensors": "illustrious",
    "trendcraft_the_peoples_style_detailer-v2.3i-4_15_2025-sdxl.safetensors": "illustrious",
    "dynamicposeil2att_alpha1.0_rank4_noxattn_900steps.safetensors": "illustrious",
    # 2026-05-03: Z-Image Turbo LoRAs whose names embed "ZIT" without a
    # word-boundary the regex can find.
    "microbikiniv2zitde.safetensors": "z_image",
    "zitnsfwlora.safetensors": "z_image",
}


# Order matters: more specific patterns first. The first match wins.
# Each entry: (compiled regex over the lowercased filename, family id).
#
# 2026-05-03 audit: walked the on-disk LoRA inventory through classify_lora()
# and found 22/48 unclassified — i.e. invisible in the family-filtered UI.
# Patterns below were widened to cover the abbreviation forms commonly used
# in community LoRAs (_ilxl_, _ixl_, IL-NOOB, IL2att, illusXL, ZIT*,
# WanAnimate / WanRelight / lightx2v). Anything still not caught by these
# patterns goes into _LORA_OVERRIDES above.
_LORA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Illustrious. Catches:
    #   * the full word "illustrious"
    #   * the abbreviations "illuxl" and "illusXL" (typo'd by some uploaders)
    #   * a word-boundary "il" optionally followed by "xl" or a digit, then
    #     a separator: e.g. _ilxl_v1, _il., -il-20, magical-girl-outfit-il-20
    #   * a word-boundary "ixl" with separator: e.g. PeronaOnePieceAnime_IXL
    #   * "il-noob" / "il_noob" — IL-NOOB (NoobAI) based merges
    (re.compile(r"illustrious|illusxl|illuxl|(?:^|[_\.\- ])il(?:xl|\d)?[_\.\-]|(?:^|[_\.\- ])ixl[_\.\-]|il[_\-]noob"), "illustrious"),
    # Z-Image. Explicit name forms + ZIT-prefixed variants (ZITnsfwLoRA,
    # MicroBikiniV2ZiTde) + standalone "turbo" (with a negative lookahead
    # to exempt the legacy sd_xl_turbo_1.0_fp16 filename).
    (re.compile(r"z_image|z-image|zimage|zit(?:nsfw|tde|[_\.\-])|turbo(?!_1\.0_fp16)"), "z_image"),
    # Wan 2.2 video. Catches the version forms plus the Animate / Relight
    # extras and the lightx2v step-distill accelerator that ships against
    # the same checkpoints.
    (re.compile(r"wan[_\.]?2\.?2|wan22|wan_i2v|wan_t2v|wan_fun|wan[_\.\-]?animate|wan[_\.\-]?relight|lightx2v"), "wan_22"),
    # LTX
    (re.compile(r"\bltx\b|ltx[_-]video|ltxv"), "ltx"),
]

# Sentinel returned when a LoRA filename matches none of the known families.
# Not a valid FAMILIES key — callers must handle by filtering it out.
UNCLASSIFIED = "unknown"


def classify_lora(filename: str) -> str:
    """Return the family id for a LoRA filename. UNCLASSIFIED if no pattern matches."""
    if not filename:
        return UNCLASSIFIED
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if base in _LORA_OVERRIDES:
        return _LORA_OVERRIDES[base]
    for pat, family in _LORA_PATTERNS:
        if pat.search(base):
            return family
    return UNCLASSIFIED


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------

def group_loras_by_family(loras: Iterable[str]) -> dict[str, list[str]]:
    """Split a flat LoRA list into {family_id: [filename, ...]}.

    Sorts each family's list alphabetically for stable UI order. LoRAs whose
    filename doesn't match any known family pattern are dropped — the frontend
    only needs per-family lists, and an "Unknown" bucket just adds noise.
    """
    out: dict[str, list[str]] = {fid: [] for fid in FAMILIES.keys()}
    for name in loras:
        fam = classify_lora(name)
        if fam == UNCLASSIFIED:
            continue
        out.setdefault(fam, []).append(name)
    for fam in out:
        out[fam].sort()
    return out


def family_summary(grouped_high: dict[str, list[str]],
                   grouped_low: dict[str, list[str]]) -> list[dict]:
    """Build the payload for the base-model dropdown.

    Returns a list of families (in sort_order), each with counts and checkpoints.
    Families with 0 LoRAs AND 0 known checkpoints are omitted to avoid clutter.
    """
    ck_by_fam = known_checkpoints_by_family()
    rows: list[dict] = []
    for fam in sorted(FAMILIES.values(), key=lambda f: f.sort_order):
        high = grouped_high.get(fam.id, [])
        low = grouped_low.get(fam.id, [])
        checkpoints = ck_by_fam.get(fam.id, [])
        if not high and not low and not checkpoints:
            continue
        rows.append({
            "id": fam.id,
            "label": fam.label,
            "description": fam.description,
            "ckpt_dir": fam.ckpt_dir,
            "lora_count_high": len(high),
            "lora_count_low": len(low),
            "checkpoints": [
                {"filename": cp.filename, "label": cp.label, "notes": cp.notes}
                for cp in checkpoints
            ],
        })
    return rows
