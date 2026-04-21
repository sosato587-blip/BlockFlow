"""Base-model taxonomy for checkpoints and LoRAs.

A "base model family" is the architecture a checkpoint / LoRA is tied to:
illustrious (SDXL-anime), sdxl (generic SDXL), z_image (Alibaba S3-DiT),
wan_22 (14B video), flux, ltx, unknown.

This module exists so the Generate-tab LoRA dropdowns can be filtered by
the selected base model — preventing the classic "I loaded a Wan LoRA
under an Illustrious checkpoint and got garbage" failure mode.

Design notes:
- Classification is filename-pattern-based. No network calls.
- Each family has a display label + which ComfyUI model-type slot it
  loads into (checkpoints / diffusion_models / etc.) — useful for the
  future Base Model Selector block that will also emit workflow overrides.
- `UNKNOWN` is a catch-all; new LoRAs fall here until we add a pattern.
  The frontend should show UNKNOWN LoRAs under a "Other / uncategorized"
  group so nothing is hidden, just unclassified.

The classifiers are intentionally permissive — a LoRA named with only a
character name and no architecture hint falls to UNKNOWN rather than
being guessed. Prefer explicit hints like `_IllustriousXL` / `_z_image`
/ `_wan22` / `_sdxl` / `_flux` / `_ltx` in LoRA filenames.
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
        label="Illustrious XL (SDXL anime)",
        description="Anime-styled SDXL derivative. Best for 2D anime / illustration.",
        ckpt_dir="checkpoints",
        sort_order=10,
    ),
    "sdxl": BaseModelFamily(
        id="sdxl",
        label="SDXL (generic)",
        description="Generic Stable Diffusion XL. Catch-all for non-Illustrious SDXL.",
        ckpt_dir="checkpoints",
        sort_order=20,
    ),
    "z_image": BaseModelFamily(
        id="z_image",
        label="Z-Image Turbo (realistic)",
        description="Alibaba S3-DiT realistic model. Use CLIPLoader + qwen_3_4b + type:lumina2.",
        ckpt_dir="diffusion_models",
        sort_order=30,
    ),
    "wan_22": BaseModelFamily(
        id="wan_22",
        label="Wan 2.2 (video, 14B)",
        description="14B video diffusion (I2V / Fun Control). Uses wan_2.1_vae.",
        ckpt_dir="diffusion_models",
        sort_order=40,
    ),
    "flux": BaseModelFamily(
        id="flux",
        label="Flux",
        description="Black Forest Labs Flux. Dev or Schnell variants.",
        ckpt_dir="diffusion_models",
        sort_order=50,
    ),
    "ltx": BaseModelFamily(
        id="ltx",
        label="LTX Video 0.9.5 (fast video)",
        description="Lightricks LTX 2B video model. ~4-6× cheaper than Wan.",
        ckpt_dir="diffusion_models",
        sort_order=60,
    ),
    "unknown": BaseModelFamily(
        id="unknown",
        label="Other / uncategorized",
        description="No family hint in filename. Review and add a pattern if this is real.",
        ckpt_dir="checkpoints",
        sort_order=999,
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
        filename="waiIllustriousSDXL_v160.safetensors",
        family="illustrious",
        label="WAI Illustrious XL v1.6.0",
        notes="Main anime checkpoint. 6.6GB, SDXL arch.",
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
# hint when possible. This map exists for historical names we can't rename.
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
}


# Order matters: more specific patterns first. The first match wins.
# Each entry: (compiled regex over the lowercased filename, family id)
_LORA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Illustrious-specific hints
    (re.compile(r"illustrious|illuxl|_il\.|_illu[_\.]"), "illustrious"),
    # Z-Image hints
    (re.compile(r"z_image|z-image|zimage|turbo(?!_1\.0_fp16)"), "z_image"),
    # Wan 2.2 video hints
    (re.compile(r"wan[_\.]?2\.?2|wan22|wan_i2v|wan_t2v|wan_fun"), "wan_22"),
    # Flux
    (re.compile(r"\bflux\b|_flux_"), "flux"),
    # LTX
    (re.compile(r"\bltx\b|ltx[_-]video|ltxv"), "ltx"),
    # Generic SDXL (only catch if nothing more specific hit)
    (re.compile(r"sdxl|xl_v\d|_xl\b"), "sdxl"),
]


def classify_lora(filename: str) -> str:
    """Return the family id for a LoRA filename. 'unknown' if no pattern matches."""
    if not filename:
        return "unknown"
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if base in _LORA_OVERRIDES:
        return _LORA_OVERRIDES[base]
    for pat, family in _LORA_PATTERNS:
        if pat.search(base):
            return family
    return "unknown"


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------

def group_loras_by_family(loras: Iterable[str]) -> dict[str, list[str]]:
    """Split a flat LoRA list into {family_id: [filename, ...]}.

    Sorts each family's list alphabetically for stable UI order.
    """
    out: dict[str, list[str]] = {fid: [] for fid in FAMILIES.keys()}
    for name in loras:
        fam = classify_lora(name)
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
        if not high and not low and not checkpoints and fam.id != "unknown":
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
