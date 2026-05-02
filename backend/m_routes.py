"""Mobile-specific routes for the /m page.

Provides:
- /api/m/generate          — quick generate (image) with model+prompt
- /api/m/status/{job_id}   — check RunPod job status
- /api/m/inventory         — list models on RunPod Network Volume

Workflows are constructed inline using known-good templates for
Z-Image Turbo and Illustrious XL. This keeps the mobile path simple
and independent of the block-based pipeline.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import base64
import tempfile
from pathlib import Path
from backend import config, services, m_store, tmpfiles

router = APIRouter()


# ============================================================
# Workflow templates
# ============================================================

NEGATIVE_DEFAULT = (
    "ugly, deformed, bad anatomy, bad hands, extra fingers, blurry, "
    "low quality, worst quality, watermark, text, signature"
)


def _split_loras_from_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize LoRA fields from a request payload into (high, low) lists.

    The mobile client (post-A4) sends ``high_loras`` / ``low_loras``. Older
    clients still send a flat ``loras`` field; we route those entries to
    the high branch and emit a one-line deprecation warning so the legacy
    callers can be tracked down.

    A caller that explicitly passes ``high_loras=[]`` or ``low_loras=[]``
    is considered to be on the new shape — the legacy ``loras`` fallback
    only kicks in when BOTH new fields are entirely absent.
    """
    high_raw = payload.get("high_loras")
    low_raw = payload.get("low_loras")
    high = list(high_raw) if high_raw is not None else []
    low = list(low_raw) if low_raw is not None else []
    if high_raw is None and low_raw is None:
        legacy = payload.get("loras") or []
        if legacy:
            print(
                "[m/loras] DEPRECATED: payload uses flat 'loras=[...]'; "
                "switch to 'high_loras' / 'low_loras'. Routing legacy "
                "entries to high_loras.",
                flush=True,
            )
            high = list(legacy)
    return high, low


def build_z_image_workflow(
    prompt: str,
    width: int = 1080,
    height: int = 1920,
    steps: int = 8,
    cfg: float = 1.0,
    seed: int | None = None,
    loras: list[dict[str, Any]] | None = None,
    high_loras: list[dict[str, Any]] | None = None,
    low_loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    negative: str = "",
) -> dict[str, Any]:
    """Z-Image Turbo workflow (CLIPLoader + qwen_3_4b + ae VAE).

    LoRAs may be supplied in either of two shapes:
      * ``high_loras=[...], low_loras=[...]`` — preferred (matches the
        desktop/mobile split UI). Z-Image is single-pass, so the two
        branches are concatenated (high → low) into one chain.
      * ``loras=[...]`` — legacy flat list. Used only when both new
        params are ``None``.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    # Resolve the effective single-pass chain. When new-shape inputs are
    # present (even if empty lists), they take precedence over legacy
    # ``loras``; the legacy field only acts as a fallback.
    if high_loras is not None or low_loras is not None:
        loras = list(high_loras or []) + list(low_loras or [])

    wf: dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2"},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": prompt},
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "ZI_mobile"},
        },
    }

    # Inject LoRA chain between UNETLoader and KSampler if requested
    if loras:
        prev_model_node = "1"
        prev_clip_node = "2"
        for i, lora in enumerate(loras):
            node_id = f"100{i}"
            wf[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model_node, 0],
                    "clip": [prev_clip_node, 0],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model_node = node_id
            prev_clip_node = node_id
        # Rewire KSampler model + CLIPTextEncode clip to the chained outputs
        wf["6"]["inputs"]["model"] = [prev_model_node, 0]
        wf["10"]["inputs"]["clip"] = [prev_clip_node, 0]
        wf["11"]["inputs"]["clip"] = [prev_clip_node, 0]

    return wf


def build_illustrious_ipadapter_workflow(
    prompt: str,
    reference_filename: str,
    ipadapter_file: str = "ip-adapter-plus_sdxl_vit-h.safetensors",
    clip_vision_file: str = "clip_vision_h.safetensors",
    weight: float = 0.7,
    weight_type: str = "linear",
    start_at: float = 0.0,
    end_at: float = 1.0,
    width: int = 1024,
    height: int = 1536,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int | None = None,
    negative: str = NEGATIVE_DEFAULT,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
) -> dict[str, Any]:
    """Illustrious XL + IP-Adapter workflow (Chara IP).

    Injects character identity from a reference image via IP-Adapter,
    preserving face/style features without needing a trained LoRA.

    Requires:
    - CLIP Vision model at models/clip_vision/ (we have clip_vision_h.safetensors)
    - IP-Adapter model at models/ipadapter/ (default: ip-adapter-plus_sdxl_vit-h)
    - Custom node: ComfyUI_IPAdapter_plus (by cubiq)
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "60": {
            "class_type": "LoadImage",
            "inputs": {"image": reference_filename},
        },
        "61": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": clip_vision_file},
        },
        "62": {
            "class_type": "IPAdapterModelLoader",
            "inputs": {"ipadapter_file": ipadapter_file},
        },
        "63": {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["1", 0],
                "ipadapter": ["62", 0],
                "image": ["60", 0],
                "clip_vision": ["61", 0],
                "weight": weight,
                "weight_type": weight_type,
                "combine_embeds": "concat",
                "start_at": start_at,
                "end_at": end_at,
                "embeds_scaling": "V only",
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": prompt},
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": negative},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["63", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "IL_charaip"},
        },
    }

    # LoRA chain — applied to the model BEFORE IPAdapter injection
    if loras:
        prev_model = "1"
        prev_clip = "1"
        prev_model_idx = 0
        prev_clip_idx = 1
        for i, lora in enumerate(loras):
            nid = f"500{i}"
            wf[nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model, prev_model_idx],
                    "clip": [prev_clip, prev_clip_idx],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model = nid
            prev_clip = nid
            prev_model_idx = 0
            prev_clip_idx = 1
        # IPAdapter takes the LoRA-modified model
        wf["63"]["inputs"]["model"] = [prev_model, 0]
        wf["10"]["inputs"]["clip"] = [prev_clip, 1]
        wf["11"]["inputs"]["clip"] = [prev_clip, 1]

    return wf


def build_illustrious_face_detailer_workflow(
    image_filename: str,
    face_prompt: str = "beautiful face, detailed eyes, sharp focus, high quality, natural skin",
    face_negative: str = "blurry, deformed, bad anatomy, extra eyes, lowres",
    bbox_model: str = "bbox/face_yolov8m.pt",
    sam_model: str = "sam_vit_b_01ec64.pth",
    use_sam: bool = True,
    denoise: float = 0.4,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int | None = None,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
    guide_size: int = 512,
    feather: int = 5,
) -> dict[str, Any]:
    """Illustrious XL + FaceDetailer (ADetailer) workflow.

    Loads a pre-generated image, auto-detects faces, and runs inpaint on each
    detected face to improve quality. Uses Impact Pack's FaceDetailer node.

    Requires custom nodes: ComfyUI-Impact-Pack (usually pre-installed in
    comfy-gen handler). Models: bbox detector + optional SAM.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "40": {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename},
        },
        "41": {
            "class_type": "UltralyticsDetectorProvider",
            "inputs": {"model_name": bbox_model},
        },
        "44": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": face_prompt},
        },
        "45": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": face_negative},
        },
        "46": {
            "class_type": "FaceDetailer",
            "inputs": {
                "image": ["40", 0],
                "model": ["1", 0],
                "clip": ["1", 1],
                "vae": ["1", 2],
                "positive": ["44", 0],
                "negative": ["45", 0],
                "bbox_detector": ["41", 0],
                "guide_size": guide_size,
                "guide_size_for": True,
                "max_size": 1024,
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
                "feather": feather,
                "noise_mask": True,
                "force_inpaint": False,
                "bbox_threshold": 0.5,
                "bbox_dilation": 10,
                "bbox_crop_factor": 3.0,
                "sam_detection_hint": "center-1",
                "sam_dilation": 0,
                "sam_threshold": 0.93,
                "sam_bbox_expansion": 0,
                "sam_mask_hint_threshold": 0.7,
                "sam_mask_hint_use_negative": "False",
                "drop_size": 10,
                "wildcard": "",
                "cycle": 1,
            },
        },
        "47": {
            "class_type": "SaveImage",
            "inputs": {"images": ["46", 0], "filename_prefix": "IL_adetailer"},
        },
    }

    # Add SAM to FaceDetailer if requested
    if use_sam:
        wf["42"] = {
            "class_type": "SAMLoader",
            "inputs": {"model_name": sam_model, "device_mode": "AUTO"},
        }
        wf["46"]["inputs"]["sam_model_opt"] = ["42", 0]

    # LoRA chain (affects the face re-generation too)
    if loras:
        prev_model = "1"
        prev_clip = "1"
        prev_model_idx = 0
        prev_clip_idx = 1
        for i, lora in enumerate(loras):
            nid = f"400{i}"
            wf[nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model, prev_model_idx],
                    "clip": [prev_clip, prev_clip_idx],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model = nid
            prev_clip = nid
            prev_model_idx = 0
            prev_clip_idx = 1
        wf["46"]["inputs"]["model"] = [prev_model, 0]
        wf["44"]["inputs"]["clip"] = [prev_clip, 1]
        wf["45"]["inputs"]["clip"] = [prev_clip, 1]

    return wf


def build_illustrious_controlnet_canny_workflow(
    prompt: str,
    reference_filename: str,
    controlnet_model: str = "diffusers_xl_canny_full.safetensors",
    controlnet_strength: float = 0.7,
    width: int = 1024,
    height: int = 1536,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int | None = None,
    negative: str = NEGATIVE_DEFAULT,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
    canny_low: int = 100,
    canny_high: int = 200,
) -> dict[str, Any]:
    """Illustrious XL + ControlNet Canny workflow.

    Uses Canny edge detection (algorithmic, no preprocessor model needed) on a
    reference image to guide composition. Great for preserving overall layout /
    pose while changing style or details.

    Requires:
    - ControlNet SDXL Canny model at /runpod-volume/models/controlnet/{controlnet_model}
    - Reference image provided via file_inputs (downloaded to reference_filename)
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "20": {
            "class_type": "LoadImage",
            "inputs": {"image": reference_filename},
        },
        "21": {
            "class_type": "CannyEdgePreprocessor",
            "inputs": {
                "image": ["20", 0],
                "low_threshold": canny_low,
                "high_threshold": canny_high,
                "resolution": 1024,
            },
        },
        "22": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": controlnet_model},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": prompt},
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": negative},
        },
        "23": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["10", 0],
                "negative": ["11", 0],
                "control_net": ["22", 0],
                "image": ["21", 0],
                "strength": controlnet_strength,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["23", 0],
                "negative": ["23", 1],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "IL_cn_canny"},
        },
    }

    if loras:
        prev_model = "1"
        prev_clip = "1"
        prev_model_idx = 0
        prev_clip_idx = 1
        for i, lora in enumerate(loras):
            nid = f"300{i}"
            wf[nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model, prev_model_idx],
                    "clip": [prev_clip, prev_clip_idx],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model = nid
            prev_clip = nid
            prev_model_idx = 0
            prev_clip_idx = 1
        wf["6"]["inputs"]["model"] = [prev_model, 0]
        wf["10"]["inputs"]["clip"] = [prev_clip, 1]
        wf["11"]["inputs"]["clip"] = [prev_clip, 1]

    return wf


def build_illustrious_inpaint_workflow(
    image_filename: str,
    mask_filename: str,
    prompt: str,
    steps: int = 25,
    cfg: float = 7.0,
    denoise: float = 0.9,
    seed: int | None = None,
    negative: str = NEGATIVE_DEFAULT,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
) -> dict[str, Any]:
    """Illustrious XL inpaint workflow.

    Requires both image_filename (source) and mask_filename (white = area to regen).
    Both should be provided via file_inputs so handler downloads them locally.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "50": {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename},
        },
        "51": {
            "class_type": "LoadImage",
            "inputs": {"image": mask_filename},  # Used as mask source (alpha or grayscale)
        },
        "52": {
            "class_type": "ImageToMask",
            "inputs": {"image": ["51", 0], "channel": "red"},  # Red channel = mask
        },
        "53": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": ["50", 0],
                "vae": ["1", 2],
                "mask": ["52", 0],
                "grow_mask_by": 6,
            },
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": prompt},
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": negative},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "latent_image": ["53", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "IL_inpaint"},
        },
    }

    # LoRA chain
    if loras:
        prev_model = "1"
        prev_clip = "1"
        prev_model_idx = 0
        prev_clip_idx = 1
        for i, lora in enumerate(loras):
            nid = f"200{i}"
            wf[nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model, prev_model_idx],
                    "clip": [prev_clip, prev_clip_idx],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model = nid
            prev_clip = nid
            prev_model_idx = 0
            prev_clip_idx = 1
        wf["6"]["inputs"]["model"] = [prev_model, 0]
        wf["10"]["inputs"]["clip"] = [prev_clip, 1]
        wf["11"]["inputs"]["clip"] = [prev_clip, 1]

    return wf


def build_wan_i2v_workflow(
    prompt: str,
    image_filename: str,
    width: int = 480,
    height: int = 832,
    length: int = 33,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 3.5,
    shift: float = 8.0,
    seed: int | None = None,
    negative: str = "static, no movement, blurry, distorted, bad quality, morphing, deformed",
    high_loras: list[dict[str, Any]] | None = None,
    low_loras: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Wan 2.2 I2V workflow (high_noise + low_noise 2-pass with ModelSamplingSD3).

    Wan 2.2 is a true dual-expert model: one UNet handles the high-noise
    early-steps pass, a separate UNet handles the low-noise late-steps
    pass. ``high_loras`` and ``low_loras`` are injected as independent
    ``LoraLoaderModelOnly`` chains between each ``UNETLoader`` and the
    corresponding ``ModelSamplingSD3`` node, mirroring the dual-pass
    structure. ``LoraLoaderModelOnly`` is used (rather than ``LoraLoader``)
    because the workflow's text encoder is a separate ``CLIPLoader``,
    not a checkpoint-bundled CLIP — there is no clip output to thread
    through.

    NOTE: Requires file_inputs to be passed alongside this workflow so the
    handler can download the input image into image_filename before execution.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        # --- Model loaders ---
        "37": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "fp8_e4m3fn",
            },
        },
        "56": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "fp8_e4m3fn",
            },
        },
        "38": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"},
        },
        "39": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},  # Critical: NOT wan2.2_vae
        },
        # --- Input image ---
        "52": {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename},
        },
        # --- Text prompts ---
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["38", 0]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["38", 0]},
        },
        # --- ModelSamplingSD3 (shift) ---
        "54": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"shift": shift, "model": ["37", 0]},
        },
        "55": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"shift": shift, "model": ["56", 0]},
        },
        # --- WanImageToVideo (conditioning + latent) ---
        "50": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": length,
                "batch_size": 1,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "vae": ["39", 0],
                "start_image": ["52", 0],
            },
        },
        # --- 2-pass sampling ---
        "57": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["54", 0],
                "positive": ["50", 0],
                "negative": ["50", 1],
                "latent_image": ["50", 2],
                "add_noise": "enable",
                "noise_seed": seed,
                "control_after_generate": "fixed",
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": steps // 2,
                "return_with_leftover_noise": "enable",
            },
        },
        "58": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["55", 0],
                "positive": ["50", 0],
                "negative": ["50", 1],
                "latent_image": ["57", 0],
                "add_noise": "disable",
                "noise_seed": seed,
                "control_after_generate": "fixed",
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": steps // 2,
                "end_at_step": 10000,
                "return_with_leftover_noise": "disable",
            },
        },
        # --- Decode + save ---
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["58", 0], "vae": ["39", 0]},
        },
        "26": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["8", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": "WAN_mobile",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            },
        },
    }

    # Dual-pass LoRA injection. high_loras chain sits between UNETLoader "37"
    # and ModelSamplingSD3 "54"; low_loras chain sits between UNETLoader "56"
    # and ModelSamplingSD3 "55". Node ids "370<i>" / "560<i>" are picked to
    # avoid collisions with the existing literals (37, 56, 50, 52, 54-58, 6-9).
    # ``_meta.title`` is included so a desktop ComfyGen block re-loading the
    # exported JSON can run the labeled-loader heuristic in lora-mapping.ts.
    def _inject_chain(
        wf_dict: dict[str, Any],
        picks: list[dict[str, Any]] | None,
        loader_id: str,
        sampling_id: str,
        id_prefix: str,
        title: str,
    ) -> None:
        if not picks:
            return
        prev = loader_id
        for i, lora in enumerate(picks):
            nid = f"{id_prefix}{i}"
            wf_dict[nid] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [prev, 0],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                },
                "_meta": {"title": title},
            }
            prev = nid
        wf_dict[sampling_id]["inputs"]["model"] = [prev, 0]

    _inject_chain(wf, high_loras, "37", "54", "370", "High Noise LoRA")
    _inject_chain(wf, low_loras, "56", "55", "560", "Low Noise LoRA")

    return wf


# ============================================================
# Wan 2.2 Animate (Kijai WanVideoWrapper flavor)
# ============================================================

WAN_ANIMATE_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_blocks"
    / "wan_animate"
    / "workflow_template.json"
)

# Default negative prompt used by the Kijai example workflow. Chinese
# "ugly list" — most users don't override this.
WAN_ANIMATE_NEGATIVE_DEFAULT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，"
    "静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
    "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
    "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，"
    "背景人很多，倒着走"
)

# Well-known node IDs in workflow_template.json that the patcher writes
# into. Pinned here so a future template regeneration that shifts ids
# trips the pytest fixtures rather than silently mis-patching at runtime.
_WAN_ANIMATE_NODE_IDS = {
    "model_loader":       "22",   # WanVideoModelLoader
    "sampler":            "27",   # WanVideoSampler
    "decode":             "28",   # WanVideoDecode
    "vae_loader":         "38",   # WanVideoVAELoader
    "ref_image":          "57",   # LoadImage (reference still)
    "animate_embeds":     "62",   # WanVideoAnimateEmbeds
    "driving_video":      "63",   # VHS_LoadVideo (motion driver)
    "text_encode":        "65",   # WanVideoTextEncodeCached
    "clip_vision_loader": "71",   # CLIPVisionLoader
    "context_options":    "110",  # WanVideoContextOptions
    "video_combine_main": "30",   # VHS_VideoCombine (audio-muxed final)
    "lora_select":        "171",  # WanVideoLoraSelectMulti
}


def _load_wan_animate_template() -> dict[str, Any]:
    """Load the API-format Wan Animate template, deep-copied so callers can mutate."""
    raw = WAN_ANIMATE_TEMPLATE_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def build_wan_animate_workflow(
    prompt: str,
    image_filename: str,
    video_filename: str,
    width: int = 832,
    height: int = 480,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 6,
    cfg: float = 5.0,
    shift: float = 1.0,
    seed: int | None = None,
    scheduler: str = "dpm++_sde",
    negative: str | None = None,
    pose_strength: float = 1.0,
    face_strength: float = 1.0,
    colormatch: str = "disabled",
    frame_window_size: int = 77,
    denoise_strength: float = 1.0,
    high_loras: list[dict[str, Any]] | None = None,
    low_loras: list[dict[str, Any]] | None = None,
    keep_default_acceleration_loras: bool = True,
    filename_prefix: str = "WanAnimate",
) -> dict[str, Any]:
    """Build a Wan 2.2 Animate (Kijai) API workflow patched with user values.

    The Kijai canvas has been pre-converted to API format and shipped as
    ``custom_blocks/wan_animate/workflow_template.json`` (33 active nodes,
    SAM 2 mask + face crop chain + BlockSwap + ContextOptions all
    preserved). This function deep-copies the template and overrides the
    well-known nodes listed in ``_WAN_ANIMATE_NODE_IDS``.

    LoRA handling:
      The template's ``WanVideoLoraSelectMulti`` (node 171) ships with
      slots 0-1 filled by the recommended ``WanAnimate_relight`` LoRA
      (strength 1.0) and the ``lightx2v`` speed-distillation LoRA
      (strength 1.2). Slots 2-4 are empty. User-supplied ``high_loras``
      / ``low_loras`` (Wan Animate is single-pass — they're concatenated)
      go into slots 2 onwards. Pass
      ``keep_default_acceleration_loras=False`` to wipe the defaults
      first; in that case ``steps`` should be raised to ~25-30.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)
    neg = negative if negative is not None else WAN_ANIMATE_NEGATIVE_DEFAULT

    wf = _load_wan_animate_template()
    nid = _WAN_ANIMATE_NODE_IDS

    # --- Reference image + driving video ---
    wf[nid["ref_image"]]["inputs"]["image"] = image_filename
    wf[nid["driving_video"]]["inputs"]["video"] = video_filename
    wf[nid["driving_video"]]["inputs"]["force_rate"] = int(fps)

    # --- Text prompts ---
    wf[nid["text_encode"]]["inputs"]["positive_prompt"] = prompt
    wf[nid["text_encode"]]["inputs"]["negative_prompt"] = neg

    # --- Animate embeds (resolution + length) ---
    embeds = wf[nid["animate_embeds"]]["inputs"]
    # The canvas wires width/height/num_frames from INTConstant nodes that
    # we drop during canvas->API conversion, so we have to fill literal
    # values here.
    embeds["width"] = int(width)
    embeds["height"] = int(height)
    embeds["num_frames"] = int(num_frames)
    embeds["frame_window_size"] = int(frame_window_size)
    embeds["pose_strength"] = float(pose_strength)
    embeds["face_strength"] = float(face_strength)
    embeds["colormatch"] = str(colormatch)
    # The driving-video resolution refs (canvas had VHS_LoadVideo's
    # custom_width/height linked to INTConstants too) — pin them to
    # match the requested output dimensions.
    wf[nid["driving_video"]]["inputs"]["custom_width"] = int(width)
    wf[nid["driving_video"]]["inputs"]["custom_height"] = int(height)

    # --- Sampler (steps / cfg / shift / seed / scheduler) ---
    sampler = wf[nid["sampler"]]["inputs"]
    sampler["steps"] = int(steps)
    sampler["cfg"] = float(cfg)
    sampler["shift"] = float(shift)
    sampler["seed"] = int(seed)
    sampler["scheduler"] = str(scheduler)
    sampler["denoise_strength"] = float(denoise_strength)

    # --- Output naming ---
    wf[nid["video_combine_main"]]["inputs"]["filename_prefix"] = filename_prefix
    wf[nid["video_combine_main"]]["inputs"]["frame_rate"] = int(fps)

    # --- LoRA chain ---
    lora_inputs = wf[nid["lora_select"]]["inputs"]
    if not keep_default_acceleration_loras:
        for i in range(5):
            lora_inputs[f"lora_{i}"] = "none"
            lora_inputs[f"strength_{i}"] = 1.0

    # Wan Animate is single-pass; concatenate high/low picks.
    user_picks: list[dict[str, Any]] = []
    user_picks.extend(high_loras or [])
    user_picks.extend(low_loras or [])
    next_slot = 2 if keep_default_acceleration_loras else 0
    for pick in user_picks:
        if next_slot > 4:
            break  # 5-slot WanVideoLoraSelectMulti — drop overflow
        name = pick.get("name") or ""
        if not name or name == "__none__":
            continue
        strength = float(pick.get("strength", 1.0))
        lora_inputs[f"lora_{next_slot}"] = name
        lora_inputs[f"strength_{next_slot}"] = strength
        next_slot += 1

    return wf


def build_illustrious_workflow(
    prompt: str,
    width: int = 1024,
    height: int = 1536,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int | None = None,
    negative: str = NEGATIVE_DEFAULT,
    loras: list[dict[str, Any]] | None = None,
    high_loras: list[dict[str, Any]] | None = None,
    low_loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
) -> dict[str, Any]:
    """Illustrious XL workflow (SDXL family, CheckpointLoaderSimple).

    See ``build_z_image_workflow`` for the LoRA payload contract; SDXL is
    likewise single-pass, so the high/low branches are concatenated into
    one ``LoraLoader`` chain.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    if high_loras is not None or low_loras is not None:
        loras = list(high_loras or []) + list(low_loras or [])

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": prompt},
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": negative},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "IL_mobile"},
        },
    }

    if loras:
        prev_model_node = "1"
        prev_clip_node = "1"
        prev_model_idx = 0
        prev_clip_idx = 1
        for i, lora in enumerate(loras):
            node_id = f"100{i}"
            wf[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model_node, prev_model_idx],
                    "clip": [prev_clip_node, prev_clip_idx],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model_node = node_id
            prev_clip_node = node_id
            prev_model_idx = 0
            prev_clip_idx = 1
        wf["6"]["inputs"]["model"] = [prev_model_node, prev_model_idx]
        wf["10"]["inputs"]["clip"] = [prev_clip_node, prev_clip_idx]
        wf["11"]["inputs"]["clip"] = [prev_clip_node, prev_clip_idx]

    return wf


# ============================================================
# Phase 12: Outpaint (extend canvas outward)
# ============================================================

def build_illustrious_outpaint_workflow(
    image_filename: str,
    prompt: str,
    pad_left: int = 0,
    pad_right: int = 0,
    pad_top: int = 0,
    pad_bottom: int = 0,
    feathering: int = 40,
    steps: int = 25,
    cfg: float = 7.0,
    denoise: float = 1.0,
    seed: int | None = None,
    negative: str = NEGATIVE_DEFAULT,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
) -> dict[str, Any]:
    """Outpaint via ImagePadForOutpaint -> VAEEncodeForInpaint -> KSampler."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "50": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "60": {
            "class_type": "ImagePadForOutpaint",
            "inputs": {
                "image": ["50", 0],
                "left": pad_left,
                "top": pad_top,
                "right": pad_right,
                "bottom": pad_bottom,
                "feathering": feathering,
            },
        },
        "61": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": ["60", 0],
                "vae": ["1", 2],
                "mask": ["60", 1],
                "grow_mask_by": 8,
            },
        },
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "latent_image": ["61", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "IL_outpaint"},
        },
    }

    if loras:
        prev_model = "1"; prev_clip = "1"
        for i, lora in enumerate(loras):
            nid = f"300{i}"
            wf[nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model, 0],
                    "clip": [prev_clip, 1],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model = nid; prev_clip = nid
        wf["6"]["inputs"]["model"] = [prev_model, 0]
        wf["10"]["inputs"]["clip"] = [prev_clip, 1]
        wf["11"]["inputs"]["clip"] = [prev_clip, 1]

    return wf


# ============================================================
# Phase 14: Character Sheet (multi-view on a wide canvas)
# ============================================================

CHARACTER_SHEET_PROMPT_SUFFIX = (
    ", character sheet, multiple views of the same character, "
    "front view, three-quarter view, side view, back view, "
    "turnaround, reference sheet, consistent character design, "
    "full body, neutral pose, white background, masterpiece"
)

def build_character_sheet_workflow(
    prompt: str,
    width: int = 2048,
    height: int = 1024,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int | None = None,
    negative: str = NEGATIVE_DEFAULT,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "dpmpp_2m_sde",
    scheduler: str = "karras",
) -> dict[str, Any]:
    """Wide canvas character turnaround (prompt-driven, SDXL Illustrious)."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    full_prompt = prompt.strip().rstrip(",") + CHARACTER_SHEET_PROMPT_SUFFIX

    wf: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": full_prompt}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "IL_charsheet"},
        },
    }

    if loras:
        prev_model = "1"; prev_clip = "1"
        for i, lora in enumerate(loras):
            nid = f"400{i}"
            wf[nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": [prev_model, 0],
                    "clip": [prev_clip, 1],
                    "lora_name": str(lora.get("name")),
                    "strength_model": float(lora.get("strength", 1.0)),
                    "strength_clip": float(lora.get("strength", 1.0)),
                },
            }
            prev_model = nid; prev_clip = nid
        wf["6"]["inputs"]["model"] = [prev_model, 0]
        wf["10"]["inputs"]["clip"] = [prev_clip, 1]
        wf["11"]["inputs"]["clip"] = [prev_clip, 1]

    return wf


# ============================================================
# Phase 16: LTX Video (fast, cheap T2V/I2V)
# ============================================================

def build_ltx_video_workflow(
    prompt: str,
    image_filename: str | None = None,
    width: int = 768,
    height: int = 512,
    length: int = 97,
    fps: int = 25,
    steps: int = 30,
    cfg: float = 3.0,
    seed: int | None = None,
    negative: str = "low quality, blurry, distorted, static, no movement",
) -> dict[str, Any]:
    """LTX Video 0.9.5 workflow. T2V if image_filename is None, otherwise I2V."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    wf: dict[str, Any] = {
        "10": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltx-video-2b-v0.9.5.safetensors"},
        },
        "11": {
            "class_type": "CLIPLoader",
            # Using fp8 (already on the volume from Flux); fp16 (~9.8GB) not needed.
            "inputs": {"clip_name": "t5xxl_fp8_e4m3fn.safetensors", "type": "ltxv"},
        },
        "20": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": prompt}},
        "21": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": negative}},
        "30": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {"width": width, "height": height, "length": length, "batch_size": 1},
        },
        "40": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["10", 0],
                "positive": ["20", 0],
                "negative": ["21", 0],
                "latent_image": ["30", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "50": {"class_type": "VAEDecode", "inputs": {"samples": ["40", 0], "vae": ["10", 2]}},
        "60": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["50", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": "LTX_mobile",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            },
        },
    }

    # I2V mode: LoadImage -> LTXVImgToVideo (replaces EmptyLTXVLatentVideo)
    if image_filename:
        wf["25"] = {"class_type": "LoadImage", "inputs": {"image": image_filename}}
        wf["30"] = {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["20", 0],
                "negative": ["21", 0],
                "vae": ["10", 2],
                "image": ["25", 0],
                "width": width,
                "height": height,
                "length": length,
                "batch_size": 1,
            },
        }
        # LTXVImgToVideo returns (positive, negative, latent)
        wf["40"]["inputs"]["positive"] = ["30", 0]
        wf["40"]["inputs"]["negative"] = ["30", 1]
        wf["40"]["inputs"]["latent_image"] = ["30", 2]

    return wf


# ============================================================
# Routes
# ============================================================

@router.post("/api/m/generate")
async def m_generate(request: Request) -> JSONResponse:
    """Submit a quick generation job to RunPod Serverless.

    Body:
      {
        "model": "z_image" | "illustrious",
        "prompt": "...",
        "width": 1080 (optional),
        "height": 1920 (optional),
        "steps": null (optional, defaults per model),
        "cfg": null (optional, defaults per model),
        "seed": null (optional, random if absent),
        "loras": [{"name": "filename.safetensors", "strength": 1.0}] (optional),
      }

    Returns:
      { "ok": true, "remote_job_id": "...", "endpoint_id": "..." }
    """
    payload = await request.json()
    model = str(payload.get("model", "z_image")).lower()
    prompt = str(payload.get("prompt", "")).strip()

    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt is required"}, status_code=400)

    width = int(payload.get("width") or (1080 if model == "z_image" else 1024))
    height = int(payload.get("height") or (1920 if model == "z_image" else 1536))
    seed = payload.get("seed")
    high_loras, low_loras = _split_loras_from_payload(payload)

    file_inputs: dict[str, Any] = {}

    if model == "z_image":
        steps = int(payload.get("steps") or 8)
        cfg = float(payload.get("cfg") or 1.0)
        sampler_name = str(payload.get("sampler_name") or "euler")
        scheduler = str(payload.get("scheduler") or "simple")
        negative = str(payload.get("negative") or "")
        workflow = build_z_image_workflow(
            prompt=prompt, width=width, height=height,
            steps=steps, cfg=cfg, seed=seed,
            high_loras=high_loras, low_loras=low_loras,
            sampler_name=sampler_name, scheduler=scheduler, negative=negative,
        )
    elif model == "illustrious":
        steps = int(payload.get("steps") or 30)
        cfg = float(payload.get("cfg") or 7.0)
        sampler_name = str(payload.get("sampler_name") or "dpmpp_2m_sde")
        scheduler = str(payload.get("scheduler") or "karras")
        negative = str(payload.get("negative") or NEGATIVE_DEFAULT)
        workflow = build_illustrious_workflow(
            prompt=prompt, width=width, height=height,
            steps=steps, cfg=cfg, seed=seed,
            negative=negative,
            high_loras=high_loras, low_loras=low_loras,
            sampler_name=sampler_name, scheduler=scheduler,
        )
    elif model == "wan_i2v":
        image_url = str(payload.get("image_url") or "").strip()
        if not image_url:
            return JSONResponse(
                {"ok": False, "error": "image_url is required for wan_i2v"},
                status_code=400,
            )
        # Default Wan dimensions
        width = int(payload.get("width") or 480)
        height = int(payload.get("height") or 832)
        length = int(payload.get("length") or 33)
        fps = int(payload.get("fps") or 16)
        steps = int(payload.get("steps") or 20)
        cfg = float(payload.get("cfg") or 3.5)
        # Image filename for handler-side download
        image_filename = "m_wan_input.png"
        workflow = build_wan_i2v_workflow(
            prompt=prompt, image_filename=image_filename,
            width=width, height=height, length=length, fps=fps,
            steps=steps, cfg=cfg, seed=seed,
            high_loras=high_loras, low_loras=low_loras,
        )
        file_inputs = {
            "52": {
                "url": image_url,
                "filename": image_filename,
                "field": "image",
            }
        }
    elif model == "wan_animate":
        image_url = str(payload.get("image_url") or "").strip()
        video_url = str(payload.get("video_url") or "").strip()
        if not image_url:
            return JSONResponse(
                {"ok": False, "error": "image_url (reference image) is required for wan_animate"},
                status_code=400,
            )
        if not video_url:
            return JSONResponse(
                {"ok": False, "error": "video_url (driving video) is required for wan_animate"},
                status_code=400,
            )
        # Defaults: 832x480 portrait, ~5-sec clip @ 16 fps, lightx2v 6 steps.
        width = int(payload.get("width") or 832)
        height = int(payload.get("height") or 480)
        num_frames = int(payload.get("length") or payload.get("num_frames") or 81)
        fps = int(payload.get("fps") or 16)
        steps = int(payload.get("steps") or 6)
        cfg = float(payload.get("cfg") or 5.0)
        shift = float(payload.get("shift") or 1.0)
        scheduler = str(payload.get("scheduler") or "dpm++_sde")
        negative = payload.get("negative")  # None -> builder default (Chinese ugly list)
        # Filenames the worker will download both inputs into.
        image_filename = "m_wan_animate_ref.png"
        video_filename = "m_wan_animate_drive.mp4"
        workflow = build_wan_animate_workflow(
            prompt=prompt, image_filename=image_filename, video_filename=video_filename,
            width=width, height=height, num_frames=num_frames, fps=fps,
            steps=steps, cfg=cfg, shift=shift, seed=seed,
            scheduler=scheduler, negative=negative,
            high_loras=high_loras, low_loras=low_loras,
        )
        file_inputs = {
            "57": {
                "url": image_url,
                "filename": image_filename,
                "field": "image",
            },
            "63": {
                "url": video_url,
                "filename": video_filename,
                "field": "video",
            },
        }
    else:
        return JSONResponse(
            {"ok": False, "error": f"unsupported model: {model} (use 'z_image', 'illustrious', 'wan_i2v', or 'wan_animate')"},
            status_code=400,
        )

    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id required (set in Advanced or backend .env)"}, status_code=500)

    job_input: dict[str, Any] = {"workflow": workflow}
    if file_inputs:
        job_input["file_inputs"] = file_inputs
        job_input["timeout"] = 900  # Wan jobs can take 5-10 min

    try:
        remote_job_id = services._submit_job(endpoint_id, job_input)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

    # Estimate and log cost
    est_cost = m_store.estimate_cost(
        model=model,
        width=width, height=height,
        steps=int(payload.get("steps") or 0),
        length=int(payload.get("length") or 0),
        fps=int(payload.get("fps") or 16),
    )
    m_store.log_cost({
        "model": model,
        "width": width, "height": height,
        "steps": int(payload.get("steps") or 0),
        "length": int(payload.get("length") or 0),
        "est_cost_usd": round(est_cost, 4),
        "remote_job_id": remote_job_id,
        "batch_id": payload.get("batch_id"),
        "preset_id": payload.get("preset_id"),
    })

    return JSONResponse({
        "ok": True,
        "remote_job_id": remote_job_id,
        "endpoint_id": endpoint_id,
        "model": model,
        "submitted_at": time.time(),
        "est_cost_usd": round(est_cost, 4),
    })


@router.get("/api/m/status/{remote_job_id}")
async def m_status(remote_job_id: str, endpoint_id: str = "") -> JSONResponse:
    """Check status of a RunPod job by its remote id.

    Accepts optional endpoint_id query param; falls back to backend config.
    """
    import traceback
    try:
        eid = (endpoint_id or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not eid:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=500)

        try:
            if config.MOCK_RUNPOD or str(remote_job_id).startswith("mock-"):
                resp = services._mock_status_response(remote_job_id)
            else:
                url = f"{config.RUNPOD_API_BASE}/{eid}/status/{remote_job_id}"
                resp = services._request_json("GET", url, None, timeout=config.HTTP_TIMEOUT_SEC)
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"runpod status call failed: {e}"}, status_code=502)

        # Merge carefully: resp might have its own 'ok' field from RunPod
        out: dict[str, Any] = {"ok": True}
        if isinstance(resp, dict):
            out.update(resp)
            out["ok"] = True  # force success marker after merge
        return JSONResponse(out)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/status] ERROR for {remote_job_id}: {e}\n{tb}", flush=True)
        return JSONResponse(
            {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": tb},
            status_code=500,
        )


# ============================================================
# Cost tracking
# ============================================================

@router.get("/api/m/cost")
async def m_cost_summary() -> JSONResponse:
    """Return aggregate cost summary: today / month / total / by model."""
    try:
        summary = m_store.cost_summary()
        return JSONResponse({"ok": True, **summary})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/m/cost/estimate")
async def m_cost_estimate(
    model: str = "z_image",
    width: int = 1080, height: int = 1920,
    steps: int = 8, length: int = 0, fps: int = 16,
) -> JSONResponse:
    """Return estimated cost for a potential generation without submitting."""
    try:
        est = m_store.estimate_cost(model=model, width=width, height=height, steps=steps, length=length, fps=fps)
        return JSONResponse({"ok": True, "est_cost_usd": round(est, 4)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ============================================================
# Presets (Template Library + Character Anchor unified)
# ============================================================

@router.get("/api/m/presets")
async def m_list_presets() -> JSONResponse:
    return JSONResponse({"ok": True, "presets": m_store.list_presets()})


@router.get("/api/m/presets/{preset_id}")
async def m_get_preset(preset_id: str) -> JSONResponse:
    p = m_store.get_preset(preset_id)
    if not p:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return JSONResponse({"ok": True, "preset": p})


@router.post("/api/m/presets")
async def m_save_preset(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"invalid json: {e}"}, status_code=400)
    if not payload.get("name"):
        return JSONResponse({"ok": False, "error": "name is required"}, status_code=400)
    if payload.get("kind") not in ("template", "character"):
        payload["kind"] = "template"
    saved = m_store.save_preset(payload)
    return JSONResponse({"ok": True, "preset": saved})


@router.delete("/api/m/presets/{preset_id}")
async def m_delete_preset(preset_id: str) -> JSONResponse:
    ok = m_store.delete_preset(preset_id)
    if not ok:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


# ============================================================
# Batch generation (prompt variations)
# ============================================================

@router.post("/api/m/batch")
async def m_batch_generate(request: Request) -> JSONResponse:
    """Submit a batch of generations with prompt variations.

    Body: {
      base: { model, prompt, width, height, ... },  // base params
      variations: [
        { prompt_overlay: "white dress, park", ... overrides },  // merged with base
        { prompt_overlay: "casual, cafe", ... },
        ...
      ],
      name?: "optional batch name"
    }

    Submits each variation to RunPod Serverless in parallel.
    Returns batch_id + list of remote_job_ids.
    """
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"invalid json: {e}"}, status_code=400)

    base = payload.get("base", {}) or {}
    variations = payload.get("variations", []) or []
    if not variations:
        return JSONResponse({"ok": False, "error": "variations array required"}, status_code=400)
    if not base.get("prompt") and not all(v.get("prompt") or v.get("prompt_overlay") for v in variations):
        return JSONResponse({"ok": False, "error": "each variation needs prompt or prompt_overlay (or base must have prompt)"}, status_code=400)

    endpoint_id = str(base.get("endpoint_id") or payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id required (in base or payload or .env)"}, status_code=500)

    # Build batch record
    batch = m_store.save_batch({
        "name": payload.get("name") or f"batch_{int(time.time())}",
        "preset_id": payload.get("preset_id"),
        "base": base,
        "variations": variations,
        "endpoint_id": endpoint_id,
        "jobs": [],
        "status": "submitting",
    })

    jobs: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, var in enumerate(variations):
        # Merge base + variation
        params = {**base, **{k: v for k, v in var.items() if k != "prompt_overlay"}}
        # Apply prompt overlay (appended to base prompt)
        overlay = str(var.get("prompt_overlay") or "").strip()
        if overlay:
            base_prompt = str(params.get("prompt") or base.get("prompt") or "")
            if base_prompt:
                params["prompt"] = f"{base_prompt}, {overlay}"
            else:
                params["prompt"] = overlay

        model = str(params.get("model", "z_image")).lower()
        prompt = str(params.get("prompt", "")).strip()
        if not prompt:
            errors.append(f"variation {i}: empty prompt")
            continue

        # Build workflow (same logic as /api/m/generate but inline)
        width = int(params.get("width") or (1080 if model == "z_image" else 1024))
        height = int(params.get("height") or (1920 if model == "z_image" else 1536))
        seed = params.get("seed")
        if seed is None:
            # For batches, vary seed each iteration
            seed = int(time.time() * 1000 + i) % (2**31)
        high_loras, low_loras = _split_loras_from_payload(params)

        if model == "z_image":
            workflow = build_z_image_workflow(
                prompt=prompt, width=width, height=height,
                steps=int(params.get("steps") or 8),
                cfg=float(params.get("cfg") or 1.0),
                seed=int(seed),
                high_loras=high_loras, low_loras=low_loras,
                sampler_name=str(params.get("sampler_name") or "euler"),
                scheduler=str(params.get("scheduler") or "simple"),
                negative=str(params.get("negative") or ""),
            )
        elif model == "illustrious":
            workflow = build_illustrious_workflow(
                prompt=prompt, width=width, height=height,
                steps=int(params.get("steps") or 30),
                cfg=float(params.get("cfg") or 7.0),
                seed=int(seed),
                negative=str(params.get("negative") or NEGATIVE_DEFAULT),
                high_loras=high_loras, low_loras=low_loras,
                sampler_name=str(params.get("sampler_name") or "dpmpp_2m_sde"),
                scheduler=str(params.get("scheduler") or "karras"),
            )
        else:
            errors.append(f"variation {i}: unsupported model '{model}' (batch supports z_image + illustrious)")
            continue

        try:
            remote_job_id = services._submit_job(endpoint_id, {"workflow": workflow})
        except Exception as e:
            errors.append(f"variation {i}: submit failed: {e}")
            continue

        est = m_store.estimate_cost(
            model=model, width=width, height=height,
            steps=int(params.get("steps") or 0),
        )
        m_store.log_cost({
            "model": model, "width": width, "height": height,
            "steps": int(params.get("steps") or 0),
            "est_cost_usd": round(est, 4),
            "remote_job_id": remote_job_id,
            "batch_id": batch["id"],
            "variation_index": i,
        })

        jobs.append({
            "variation_index": i,
            "remote_job_id": remote_job_id,
            "model": model,
            "prompt": prompt,
            "est_cost_usd": round(est, 4),
            "status": "IN_QUEUE",
        })

    # Update batch with final jobs list
    batch["jobs"] = jobs
    batch["status"] = "running" if jobs else "failed"
    if errors:
        batch["errors"] = errors
    m_store.save_batch(batch)

    return JSONResponse({
        "ok": True,
        "batch_id": batch["id"],
        "jobs_submitted": len(jobs),
        "errors": errors if errors else None,
        "batch": batch,
    })


@router.get("/api/m/batch/{batch_id}")
async def m_get_batch(batch_id: str) -> JSONResponse:
    """Fetch batch status. Also refreshes remote job statuses for in-flight jobs."""
    batch = m_store.get_batch(batch_id)
    if not batch:
        return JSONResponse({"ok": False, "error": "batch not found"}, status_code=404)

    # Refresh in-flight job statuses
    endpoint_id = config.RUNPOD_ENDPOINT_ID
    updated = False
    for job in batch.get("jobs", []):
        if job.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
            continue
        rjid = job.get("remote_job_id")
        if not rjid:
            continue
        try:
            url = f"{config.RUNPOD_API_BASE}/{endpoint_id}/status/{rjid}"
            resp = services._request_json("GET", url, None, timeout=10)
            new_status = str(resp.get("status", "UNKNOWN")).upper()
            if new_status != job.get("status"):
                job["status"] = new_status
                if new_status == "COMPLETED":
                    output = resp.get("output", {})
                    url = output.get("url") or output.get("video_url")
                    if url:
                        job["output_url"] = url
                updated = True
        except Exception as e:
            job["last_error"] = str(e)

    if updated:
        # Compute overall batch status
        statuses = [j.get("status") for j in batch.get("jobs", [])]
        if all(s in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT") for s in statuses):
            if all(s == "COMPLETED" for s in statuses):
                batch["status"] = "completed"
            elif all(s in ("FAILED", "CANCELLED", "TIMED_OUT") for s in statuses):
                batch["status"] = "failed"
            else:
                batch["status"] = "partial"
        else:
            batch["status"] = "running"
        m_store.save_batch(batch)

    return JSONResponse({"ok": True, "batch": batch})


@router.get("/api/m/batches")
async def m_list_batches() -> JSONResponse:
    return JSONResponse({"ok": True, "batches": m_store.list_batches()})


@router.delete("/api/m/batch/{batch_id}")
async def m_delete_batch(batch_id: str) -> JSONResponse:
    ok = m_store.delete_batch(batch_id)
    if not ok:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


# ============================================================
# Publications tracker
# ============================================================

@router.get("/api/m/publications")
async def m_list_publications() -> JSONResponse:
    return JSONResponse({"ok": True, "publications": m_store.list_publications()})


@router.post("/api/m/publications")
async def m_save_publication(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"invalid json: {e}"}, status_code=400)
    if not payload.get("image_url"):
        return JSONResponse({"ok": False, "error": "image_url required"}, status_code=400)
    saved = m_store.save_publication(payload)
    return JSONResponse({"ok": True, "publication": saved})


@router.delete("/api/m/publications/{pub_id}")
async def m_delete_publication(pub_id: str) -> JSONResponse:
    ok = m_store.delete_publication(pub_id)
    if not ok:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


# ============================================================
# Schedules
# ============================================================

@router.get("/api/m/schedules")
async def m_list_schedules() -> JSONResponse:
    return JSONResponse({"ok": True, "schedules": m_store.list_schedules()})


@router.post("/api/m/schedules")
async def m_save_schedule(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"invalid json: {e}"}, status_code=400)
    if not payload.get("name"):
        return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    saved = m_store.save_schedule(payload)
    return JSONResponse({"ok": True, "schedule": saved})


@router.delete("/api/m/schedules/{sched_id}")
async def m_delete_schedule(sched_id: str) -> JSONResponse:
    ok = m_store.delete_schedule(sched_id)
    if not ok:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


# ============================================================
# Inventory (existing, kept at end)
# ============================================================

# ============================================================
# Upload helper (base64 PNG → tmpfiles.org)
# ============================================================

@router.post("/api/m/upload")
async def m_upload(request: Request) -> JSONResponse:
    """Upload a base64-encoded blob to tmpfiles.org and return public URL.

    Body: { "data": "data:image/png;base64,iVBOR...", "filename": "mask.png" (optional) }
    Returns: { "ok": true, "url": "https://tmpfiles.org/dl/..." }

    Accepts both images and short videos. tmpfiles.org caps free uploads
    at ~100 MB and the URL expires after ~1 hour, which is enough for the
    Wan I2V / Wan Animate driving-video flow (worker pulls the file
    within 1-3 minutes of submission).
    """
    import traceback
    try:
        payload = await request.json()
        data_uri = str(payload.get("data", "")).strip()
        filename = str(payload.get("filename") or "upload.png").strip()
        if not data_uri:
            return JSONResponse({"ok": False, "error": "data required (base64 data URI)"}, status_code=400)

        if data_uri.startswith("data:"):
            _, _, data_uri = data_uri.partition(",")
        try:
            blob = base64.b64decode(data_uri)
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"base64 decode failed: {e}"}, status_code=400)

        # 100 MB ceiling matches tmpfiles.org's free-tier limit. The
        # original ceiling was 20 MB (image-only era) — bumped so short
        # MP4 driving videos (5-10 sec, 720p, ~30-60 MB typical) fit.
        if len(blob) < 64 or len(blob) > 100 * 1024 * 1024:
            return JSONResponse(
                {"ok": False, "error": f"blob size out of range ({len(blob)} bytes; allowed 64 B – 100 MB)"},
                status_code=400,
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix or ".png") as tf:
            tf.write(blob)
            tmp_path = Path(tf.name)
        try:
            url = tmpfiles.upload_to_tmpfiles(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

        return JSONResponse({"ok": True, "url": url, "size_bytes": len(blob)})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/upload] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


# ============================================================
# Chara IP (IP-Adapter — character identity injection)
# ============================================================

@router.post("/api/m/generate_charaip")
async def m_generate_charaip(request: Request) -> JSONResponse:
    """Submit IP-Adapter-guided generation (character identity via reference image).

    Body: {
      reference_image_url: "https://...",
      prompt: "...",
      ipadapter_weight: 0.7 (default),
      ipadapter_file: "ip-adapter-plus_sdxl_vit-h.safetensors" (optional),
      weight_type: "linear" (default, other: "ease in", "ease out", "style transfer"),
      start_at: 0.0, end_at: 1.0,
      standard: width, height, steps, cfg, seed, negative, loras, sampler, scheduler
      endpoint_id (optional)
    }
    """
    import traceback
    try:
        payload = await request.json()
        reference_url = str(payload.get("reference_image_url") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        if not reference_url:
            return JSONResponse({"ok": False, "error": "reference_image_url required"}, status_code=400)
        if not prompt:
            return JSONResponse({"ok": False, "error": "prompt required"}, status_code=400)

        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        seed = payload.get("seed")
        loras = payload.get("loras") or []
        reference_filename = "m_charaip_ref.png"

        workflow = build_illustrious_ipadapter_workflow(
            prompt=prompt,
            reference_filename=reference_filename,
            ipadapter_file=str(payload.get("ipadapter_file") or "ip-adapter-plus_sdxl_vit-h.safetensors"),
            clip_vision_file=str(payload.get("clip_vision_file") or "clip_vision_h.safetensors"),
            weight=float(payload.get("ipadapter_weight") or 0.7),
            weight_type=str(payload.get("weight_type") or "linear"),
            start_at=float(payload.get("start_at") or 0.0),
            end_at=float(payload.get("end_at") or 1.0),
            width=int(payload.get("width") or 1024),
            height=int(payload.get("height") or 1536),
            steps=int(payload.get("steps") or 30),
            cfg=float(payload.get("cfg") or 7.0),
            seed=int(seed) if seed is not None else None,
            negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
            loras=loras,
            sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
            scheduler=str(payload.get("scheduler") or "karras"),
        )

        file_inputs = {
            "60": {"url": reference_url, "filename": reference_filename, "field": "image"},
        }

        try:
            remote_job_id = services._submit_job(endpoint_id, {
                "workflow": workflow,
                "file_inputs": file_inputs,
                "timeout": 600,
            })
        except Exception as e:
            err_str = str(e)
            if "IPAdapter" in err_str or "ipadapter" in err_str.lower():
                return JSONResponse({
                    "ok": False,
                    "error": "IP-Adapter node or model missing. See /api/m/charaip_dl_info.",
                    "detail": err_str,
                }, status_code=424)
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        est = m_store.estimate_cost(
            model="illustrious",
            width=int(payload.get("width") or 1024),
            height=int(payload.get("height") or 1536),
            steps=int(payload.get("steps") or 30),
        )
        m_store.log_cost({
            "model": "illustrious_charaip",
            "width": int(payload.get("width") or 1024),
            "height": int(payload.get("height") or 1536),
            "steps": int(payload.get("steps") or 30),
            "est_cost_usd": round(est, 4),
            "remote_job_id": remote_job_id,
        })

        return JSONResponse({
            "ok": True,
            "remote_job_id": remote_job_id,
            "endpoint_id": endpoint_id,
            "est_cost_usd": round(est, 4),
            "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/generate_charaip] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/m/charaip_dl_info")
async def m_charaip_dl_info() -> JSONResponse:
    """DL info for IP-Adapter dependencies."""
    return JSONResponse({
        "ok": True,
        "models": [
            {
                "filename": "ip-adapter-plus_sdxl_vit-h.safetensors",
                "size_mb": 1050,
                "source_url": "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors",
                "description": "IP-Adapter PLUS for SDXL (general identity preservation). Recommended default.",
            },
            {
                "filename": "ip-adapter-plus-face_sdxl_vit-h.safetensors",
                "size_mb": 1050,
                "source_url": "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors",
                "description": "IP-Adapter PLUS FACE for SDXL (face-focused, stronger identity lock).",
            },
        ],
        "install_location": "/runpod-volume/models/ipadapter/",
        "clip_vision_already_available": "clip_vision_h.safetensors",
        "custom_nodes_required": ["ComfyUI_IPAdapter_plus"],
    })


# ============================================================
# ADetailer / FaceDetailer (auto fix faces / hands)
# ============================================================

@router.post("/api/m/adetailer")
async def m_adetailer(request: Request) -> JSONResponse:
    """Run ADetailer (FaceDetailer) post-process on an existing image.

    Body: {
      image_url: "https://...",    // source image to fix
      face_prompt: "..." (optional, default: good face prompt),
      face_negative: "..." (optional),
      denoise: 0.4 (default),
      steps: 20, cfg: 7.0,
      seed, loras, sampler_name, scheduler (optional),
      use_sam: true (default),
      endpoint_id (optional)
    }
    """
    import traceback
    try:
        payload = await request.json()
        image_url = str(payload.get("image_url") or "").strip()
        if not image_url:
            return JSONResponse({"ok": False, "error": "image_url required"}, status_code=400)

        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        seed = payload.get("seed")
        loras = payload.get("loras") or []
        image_filename = "m_adet_src.png"

        workflow = build_illustrious_face_detailer_workflow(
            image_filename=image_filename,
            face_prompt=str(payload.get("face_prompt") or "beautiful face, detailed eyes, sharp focus, high quality, natural skin"),
            face_negative=str(payload.get("face_negative") or "blurry, deformed, bad anatomy, extra eyes, lowres"),
            bbox_model=str(payload.get("bbox_model") or "bbox/face_yolov8m.pt"),
            sam_model=str(payload.get("sam_model") or "sam_vit_b_01ec64.pth"),
            use_sam=bool(payload.get("use_sam", True)),
            denoise=float(payload.get("denoise") or 0.4),
            steps=int(payload.get("steps") or 20),
            cfg=float(payload.get("cfg") or 7.0),
            seed=int(seed) if seed is not None else None,
            loras=loras,
            sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
            scheduler=str(payload.get("scheduler") or "karras"),
            guide_size=int(payload.get("guide_size") or 512),
            feather=int(payload.get("feather") or 5),
        )

        file_inputs = {
            "40": {"url": image_url, "filename": image_filename, "field": "image"},
        }

        try:
            remote_job_id = services._submit_job(endpoint_id, {
                "workflow": workflow,
                "file_inputs": file_inputs,
                "timeout": 600,
            })
        except Exception as e:
            err_str = str(e)
            if "FaceDetailer" in err_str or "UltralyticsDetectorProvider" in err_str or "Impact" in err_str:
                return JSONResponse({
                    "ok": False,
                    "error": "ADetailer node (Impact Pack) or model missing. See /api/m/adetailer_dl_info for install instructions.",
                    "detail": err_str,
                }, status_code=424)
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        est = m_store.estimate_cost(model="illustrious", width=1024, height=1024, steps=int(payload.get("steps") or 20))
        m_store.log_cost({
            "model": "illustrious_adetailer",
            "steps": int(payload.get("steps") or 20),
            "est_cost_usd": round(est, 4),
            "remote_job_id": remote_job_id,
        })

        return JSONResponse({
            "ok": True,
            "remote_job_id": remote_job_id,
            "endpoint_id": endpoint_id,
            "est_cost_usd": round(est, 4),
            "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/adetailer] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/m/adetailer_dl_info")
async def m_adetailer_dl_info() -> JSONResponse:
    """DL info for ADetailer dependencies."""
    endpoint_id = config.RUNPOD_ENDPOINT_ID
    return JSONResponse({
        "ok": True,
        "models": [
            {
                "filename": "bbox/face_yolov8m.pt",
                "size_mb": 52,
                "source_url": "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8m.pt",
                "description": "Face bbox detector (YOLOv8m). Required for FaceDetailer.",
            },
            {
                "filename": "bbox/hand_yolov8s.pt",
                "size_mb": 22,
                "source_url": "https://huggingface.co/Bingsu/adetailer/resolve/main/hand_yolov8s.pt",
                "description": "Hand bbox detector (YOLOv8s). For future hand fix.",
            },
            {
                "filename": "sam_vit_b_01ec64.pth",
                "size_mb": 375,
                "source_url": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
                "description": "Segment Anything (base). Better masking for FaceDetailer.",
            },
        ],
        "install_locations": {
            "bbox/face_yolov8m.pt": "/runpod-volume/models/ultralytics/bbox/",
            "bbox/hand_yolov8s.pt": "/runpod-volume/models/ultralytics/bbox/",
            "sam_vit_b_01ec64.pth": "/runpod-volume/models/sams/",
        },
        "custom_nodes_required": ["ComfyUI-Impact-Pack"],
        "endpoint_id": endpoint_id,
    })


# ============================================================
# ControlNet (composition control via reference image)
# ============================================================

@router.post("/api/m/generate_controlnet")
async def m_generate_controlnet(request: Request) -> JSONResponse:
    """Submit a ControlNet-guided generation.

    Body: {
      reference_image_url: "https://...",   // reference photo for composition
      controlnet_type: "canny",             // only 'canny' supported for now
      controlnet_model: "controlnet-canny-sdxl-1.0.safetensors" (optional),
      controlnet_strength: 0.7,
      prompt: "...",
      loras, width, height, steps, cfg, seed, negative, sampler, scheduler (optional)
      canny_low: 100, canny_high: 200 (optional)
      endpoint_id (optional)
    }
    """
    import traceback
    try:
        payload = await request.json()
        reference_url = str(payload.get("reference_image_url") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        if not reference_url:
            return JSONResponse({"ok": False, "error": "reference_image_url required"}, status_code=400)
        if not prompt:
            return JSONResponse({"ok": False, "error": "prompt required"}, status_code=400)

        cn_type = str(payload.get("controlnet_type") or "canny").lower()
        if cn_type != "canny":
            return JSONResponse({"ok": False, "error": f"unsupported controlnet_type: {cn_type} (only 'canny' for now)"}, status_code=400)

        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        controlnet_model = str(payload.get("controlnet_model") or "diffusers_xl_canny_full.safetensors").strip()
        seed = payload.get("seed")
        loras = payload.get("loras") or []
        reference_filename = "m_cn_ref.png"

        workflow = build_illustrious_controlnet_canny_workflow(
            prompt=prompt,
            reference_filename=reference_filename,
            controlnet_model=controlnet_model,
            controlnet_strength=float(payload.get("controlnet_strength") or 0.7),
            width=int(payload.get("width") or 1024),
            height=int(payload.get("height") or 1536),
            steps=int(payload.get("steps") or 30),
            cfg=float(payload.get("cfg") or 7.0),
            seed=int(seed) if seed is not None else None,
            negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
            loras=loras,
            sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
            scheduler=str(payload.get("scheduler") or "karras"),
            canny_low=int(payload.get("canny_low") or 100),
            canny_high=int(payload.get("canny_high") or 200),
        )

        file_inputs = {
            "20": {"url": reference_url, "filename": reference_filename, "field": "image"},
        }

        try:
            remote_job_id = services._submit_job(endpoint_id, {
                "workflow": workflow,
                "file_inputs": file_inputs,
                "timeout": 600,
            })
        except Exception as e:
            err_str = str(e)
            # Detect missing ControlNet model (common first-run failure)
            if "controlnet" in err_str.lower() or "ControlNetLoader" in err_str:
                return JSONResponse({
                    "ok": False,
                    "error": f"ControlNet model '{controlnet_model}' not found on volume. See /api/m/controlnet_dl_info for download instructions.",
                    "detail": err_str,
                }, status_code=424)
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        est = m_store.estimate_cost(
            model="illustrious", width=int(payload.get("width") or 1024),
            height=int(payload.get("height") or 1536), steps=int(payload.get("steps") or 30),
        )
        m_store.log_cost({
            "model": "illustrious_controlnet_canny",
            "width": int(payload.get("width") or 1024),
            "height": int(payload.get("height") or 1536),
            "steps": int(payload.get("steps") or 30),
            "est_cost_usd": round(est, 4),
            "remote_job_id": remote_job_id,
        })

        return JSONResponse({
            "ok": True,
            "remote_job_id": remote_job_id,
            "endpoint_id": endpoint_id,
            "est_cost_usd": round(est, 4),
            "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/generate_controlnet] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/m/controlnet_dl_info")
async def m_controlnet_dl_info() -> JSONResponse:
    """Return ControlNet model download info for the UI."""
    endpoint_id = config.RUNPOD_ENDPOINT_ID
    return JSONResponse({
        "ok": True,
        "installed_models": [],  # TODO: query list_models with model_type=controlnet
        "recommended_models": [
            {
                "filename": "diffusers_xl_canny_full.safetensors",
                "type": "canny",
                "size_mb": 2500,
                "source_url": "https://huggingface.co/diffusers/controlnet-canny-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors",
                "description": "Official ControlNet Canny for SDXL (works with Illustrious).",
                "dl_cmd_pwsh": '$b = @{ input = @{ command = "download"; downloads = @(@{ source = "url"; url = "https://huggingface.co/diffusers/controlnet-canny-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors"; dest = "controlnet"; filename = "diffusers_xl_canny_full.safetensors" }) } } | ConvertTo-Json -Depth 10; Invoke-RestMethod -Uri "https://api.runpod.ai/v2/' + endpoint_id + '/run" -Method POST -Headers @{"Authorization" = "Bearer $env:RUNPOD_API_KEY"; "Content-Type" = "application/json"} -Body $b',
            },
            {
                "filename": "controlnet-openpose-sdxl-1.0.safetensors",
                "type": "openpose",
                "size_mb": 2500,
                "source_url": "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors",
                "description": "Thibaud's OpenPose for SDXL. Pose control from skeleton input.",
                "note": "Also requires preprocessor models (body_pose, hand_pose, face). Future phase.",
            },
        ],
        "install_location": "/runpod-volume/models/controlnet/",
    })


# ============================================================
# Inpaint (partial regeneration)
# ============================================================

@router.post("/api/m/inpaint")
async def m_inpaint(request: Request) -> JSONResponse:
    """Submit an inpaint generation.

    Body: {
      image_url: source image URL,
      mask_url: mask PNG URL (red channel = area to regenerate),
      prompt: "...",
      negative, steps, cfg, denoise, seed, loras, endpoint_id (optional)
    }
    """
    import traceback
    try:
        payload = await request.json()
        image_url = str(payload.get("image_url") or "").strip()
        mask_url = str(payload.get("mask_url") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()

        if not image_url:
            return JSONResponse({"ok": False, "error": "image_url required"}, status_code=400)
        if not mask_url:
            return JSONResponse({"ok": False, "error": "mask_url required"}, status_code=400)
        if not prompt:
            return JSONResponse({"ok": False, "error": "prompt required"}, status_code=400)

        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        seed = payload.get("seed")
        loras = payload.get("loras") or []

        image_filename = "m_inpaint_src.png"
        mask_filename = "m_inpaint_mask.png"

        workflow = build_illustrious_inpaint_workflow(
            image_filename=image_filename,
            mask_filename=mask_filename,
            prompt=prompt,
            steps=int(payload.get("steps") or 25),
            cfg=float(payload.get("cfg") or 7.0),
            denoise=float(payload.get("denoise") or 0.9),
            seed=int(seed) if seed is not None else None,
            negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
            loras=loras,
            sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
            scheduler=str(payload.get("scheduler") or "karras"),
        )

        file_inputs = {
            "50": {"url": image_url, "filename": image_filename, "field": "image"},
            "51": {"url": mask_url, "filename": mask_filename, "field": "image"},
        }

        try:
            remote_job_id = services._submit_job(endpoint_id, {
                "workflow": workflow,
                "file_inputs": file_inputs,
                "timeout": 600,
            })
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        est_cost = m_store.estimate_cost(model="illustrious", width=1024, height=1536, steps=int(payload.get("steps") or 25))
        m_store.log_cost({
            "model": "illustrious_inpaint",
            "steps": int(payload.get("steps") or 25),
            "est_cost_usd": round(est_cost, 4),
            "remote_job_id": remote_job_id,
        })

        return JSONResponse({
            "ok": True,
            "remote_job_id": remote_job_id,
            "endpoint_id": endpoint_id,
            "est_cost_usd": round(est_cost, 4),
            "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/inpaint] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


# ============================================================
# Job cancel + logs viewer
# ============================================================

@router.post("/api/m/cancel/{remote_job_id}")
async def m_cancel(remote_job_id: str, endpoint_id: str = "") -> JSONResponse:
    """Force-cancel a RunPod Serverless job."""
    import traceback
    try:
        eid = (endpoint_id or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not eid:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)
        try:
            if config.MOCK_RUNPOD or str(remote_job_id).startswith("mock-"):
                resp = {"id": remote_job_id, "status": "CANCELLED"}
            else:
                url = f"{config.RUNPOD_API_BASE}/{eid}/cancel/{remote_job_id}"
                resp = services._request_json("POST", url, None, timeout=30)
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"cancel call failed: {e}"}, status_code=502)
        return JSONResponse({"ok": True, "cancelled_job_id": remote_job_id, **(resp if isinstance(resp, dict) else {})})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/cancel] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/m/logs")
async def m_logs(tail: int = 100, filter_level: str = "") -> JSONResponse:
    """Return recent BlockFlow log lines for in-UI debugging.

    Reads from C:\\Users\\sato\\logs\\blockflow_YYYY-MM-DD.log (or configurable path).
    Falls back to searching ~/logs and %USERPROFILE%/logs.
    """
    import glob
    import os as _os
    try:
        # Try common log locations
        candidates: list[str] = []
        home = _os.path.expanduser("~")
        today = time.strftime("%Y-%m-%d")
        for base in [
            f"C:\\Users\\sato\\logs",
            f"C:\\Users\\socr0\\logs",
            _os.path.join(home, "logs"),
        ]:
            candidates.extend(glob.glob(f"{base}/blockflow_*.log"))
            candidates.extend(glob.glob(f"{base}/blockflow_{today}*.log"))
        # Deduplicate and sort by modification time
        candidates = sorted(set(candidates), key=lambda p: _os.path.getmtime(p) if _os.path.exists(p) else 0, reverse=True)
        if not candidates:
            return JSONResponse({"ok": False, "error": "no log files found", "searched": [
                f"C:\\Users\\sato\\logs", f"C:\\Users\\socr0\\logs", _os.path.join(home, "logs"),
            ]})

        log_path = candidates[0]
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Take tail
        lines = lines[-max(10, min(tail, 5000)):]
        # Optional filter
        if filter_level:
            lf = filter_level.lower()
            lines = [ln for ln in lines if lf in ln.lower()]

        return JSONResponse({
            "ok": True,
            "log_path": log_path,
            "line_count": len(lines),
            "lines": lines,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/m/inventory")
async def m_inventory() -> JSONResponse:
    """List models on the RunPod Network Volume across all known directories.

    Calls list_models for each model_type in parallel, aggregates results.
    Best-effort: tolerates individual category failures.
    """
    import traceback
    try:
        return _do_inventory()
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/inventory] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse(
            {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": tb},
            status_code=500,
        )


def _do_inventory() -> JSONResponse:
    """Actual inventory implementation wrapped by m_inventory for error capture."""
    endpoint_id = config.RUNPOD_ENDPOINT_ID
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "RUNPOD_ENDPOINT_ID not configured"}, status_code=500)

    model_types = [
        "checkpoints",
        "diffusion_models",
        "text_encoders",
        "vae",
        "clip_vision",
        "loras",
        "upscale_models",
        "controlnet",
    ]

    inventory: dict[str, Any] = {}
    errors: dict[str, str] = {}

    # Submit all jobs first (parallel)
    submit_url = f"{config.RUNPOD_API_BASE}/{endpoint_id}/run"
    job_ids: dict[str, str] = {}
    for mt in model_types:
        try:
            resp = services._request_json(
                "POST", submit_url,
                {"input": {"command": "list_models", "model_type": mt}},
                timeout=15,
            )
            jid = resp.get("id")
            if jid:
                job_ids[mt] = str(jid)
            else:
                errors[mt] = f"no job id in submit response: {resp}"
        except Exception as e:
            errors[mt] = f"submit failed: {e}"

    # Poll all (with timeout per category)
    deadline = time.time() + 120  # 2 min total
    for mt, jid in job_ids.items():
        status_url = f"{config.RUNPOD_API_BASE}/{endpoint_id}/status/{jid}"
        while time.time() < deadline:
            try:
                resp = services._request_json("GET", status_url, None, timeout=10)
                status = str(resp.get("status", "")).upper()
                if status == "COMPLETED":
                    output = resp.get("output", {})
                    files = output.get("files", []) if isinstance(output, dict) else []
                    inventory[mt] = files
                    break
                if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                    errors[mt] = f"status={status}"
                    break
            except Exception as e:
                errors[mt] = f"status fetch failed: {e}"
                break
            time.sleep(3)
        else:
            errors[mt] = "polling timeout"

    # Compute totals
    totals: dict[str, dict[str, Any]] = {}
    grand_files = 0
    grand_mb = 0.0
    for mt, files in inventory.items():
        if not isinstance(files, list):
            continue
        n = len(files)
        mb = sum(float(f.get("size_mb", 0)) for f in files if isinstance(f, dict))
        totals[mt] = {"count": n, "size_mb": round(mb, 1)}
        grand_files += n
        grand_mb += mb

    return JSONResponse({
        "ok": True,
        "inventory": inventory,
        "totals": totals,
        "grand_total": {"files": grand_files, "size_mb": round(grand_mb, 1)},
        "errors": errors if errors else None,
        "fetched_at": time.time(),
    })


# ============================================================
# Phase 12 / 14 / 16 endpoints
# ============================================================

@router.post("/api/m/outpaint")
async def m_outpaint(request: Request) -> JSONResponse:
    """Outpaint (extend canvas). Body: image_url, prompt, pad_left/right/top/bottom, ..."""
    import traceback
    try:
        payload = await request.json()
        image_url = str(payload.get("image_url") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        if not image_url or not prompt:
            return JSONResponse({"ok": False, "error": "image_url and prompt required"}, status_code=400)

        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        image_filename = "m_outpaint_src.png"
        seed = payload.get("seed")
        wf = build_illustrious_outpaint_workflow(
            image_filename=image_filename,
            prompt=prompt,
            pad_left=int(payload.get("pad_left") or 0),
            pad_right=int(payload.get("pad_right") or 0),
            pad_top=int(payload.get("pad_top") or 0),
            pad_bottom=int(payload.get("pad_bottom") or 0),
            feathering=int(payload.get("feathering") or 40),
            steps=int(payload.get("steps") or 25),
            cfg=float(payload.get("cfg") or 7.0),
            denoise=float(payload.get("denoise") or 1.0),
            seed=int(seed) if seed is not None else None,
            negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
            loras=payload.get("loras") or [],
            sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
            scheduler=str(payload.get("scheduler") or "karras"),
        )
        file_inputs = {"50": {"url": image_url, "filename": image_filename, "field": "image"}}

        try:
            remote_job_id = services._submit_job(endpoint_id, {
                "workflow": wf, "file_inputs": file_inputs, "timeout": 600,
            })
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        est = m_store.estimate_cost(model="illustrious", width=1024, height=1536, steps=int(payload.get("steps") or 25))
        m_store.log_cost({
            "model": "illustrious_outpaint",
            "steps": int(payload.get("steps") or 25),
            "est_cost_usd": round(est, 4),
            "remote_job_id": remote_job_id,
        })
        return JSONResponse({
            "ok": True, "remote_job_id": remote_job_id, "endpoint_id": endpoint_id,
            "est_cost_usd": round(est, 4), "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/outpaint] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.post("/api/m/character_sheet")
async def m_character_sheet(request: Request) -> JSONResponse:
    """Generate a character turnaround sheet (wide canvas, multi-view)."""
    import traceback
    try:
        payload = await request.json()
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            return JSONResponse({"ok": False, "error": "prompt required"}, status_code=400)
        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        seed = payload.get("seed")
        width = int(payload.get("width") or 2048)
        height = int(payload.get("height") or 1024)
        steps = int(payload.get("steps") or 30)
        wf = build_character_sheet_workflow(
            prompt=prompt,
            width=width, height=height, steps=steps,
            cfg=float(payload.get("cfg") or 7.0),
            seed=int(seed) if seed is not None else None,
            negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
            loras=payload.get("loras") or [],
            sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
            scheduler=str(payload.get("scheduler") or "karras"),
        )
        try:
            remote_job_id = services._submit_job(endpoint_id, {"workflow": wf, "timeout": 600})
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        est = m_store.estimate_cost(model="illustrious", width=width, height=height, steps=steps)
        m_store.log_cost({
            "model": "character_sheet", "steps": steps,
            "est_cost_usd": round(est, 4), "remote_job_id": remote_job_id,
        })
        return JSONResponse({
            "ok": True, "remote_job_id": remote_job_id, "endpoint_id": endpoint_id,
            "est_cost_usd": round(est, 4), "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/character_sheet] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.post("/api/m/ltx_video")
async def m_ltx_video(request: Request) -> JSONResponse:
    """LTX Video generation (T2V or I2V). Requires LTX model + t5xxl text encoder on RunPod."""
    import traceback
    try:
        payload = await request.json()
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            return JSONResponse({"ok": False, "error": "prompt required"}, status_code=400)
        endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
        if not endpoint_id:
            return JSONResponse({"ok": False, "error": "endpoint_id required"}, status_code=400)

        image_url = str(payload.get("image_url") or "").strip()
        seed = payload.get("seed")
        width = int(payload.get("width") or 768)
        height = int(payload.get("height") or 512)
        length = int(payload.get("length") or 97)
        steps = int(payload.get("steps") or 30)

        image_filename = "m_ltx_src.png" if image_url else None
        wf = build_ltx_video_workflow(
            prompt=prompt, image_filename=image_filename,
            width=width, height=height, length=length,
            fps=int(payload.get("fps") or 25),
            steps=steps, cfg=float(payload.get("cfg") or 3.0),
            seed=int(seed) if seed is not None else None,
            negative=str(payload.get("negative") or "low quality, blurry, static, no movement"),
        )
        file_inputs = None
        if image_url:
            file_inputs = {"25": {"url": image_url, "filename": image_filename, "field": "image"}}

        job_body: dict[str, Any] = {"workflow": wf, "timeout": 900}
        if file_inputs:
            job_body["file_inputs"] = file_inputs
        try:
            remote_job_id = services._submit_job(endpoint_id, job_body)
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

        # LTX is ~4-6x cheaper than Wan — use a flat low estimate
        est = round(0.02 + 0.001 * steps + 0.0005 * length, 4)
        m_store.log_cost({
            "model": "ltx_video",
            "steps": steps, "length": length,
            "est_cost_usd": est, "remote_job_id": remote_job_id,
        })
        return JSONResponse({
            "ok": True, "remote_job_id": remote_job_id, "endpoint_id": endpoint_id,
            "est_cost_usd": est, "mode": "i2v" if image_url else "t2v",
            "submitted_at": time.time(),
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[m/ltx_video] ERROR: {e}\n{tb}", flush=True)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/m/ltx_dl_info")
async def m_ltx_dl_info() -> JSONResponse:
    """Return DL payload for LTX Video model + text encoder."""
    return JSONResponse({
        "ok": True,
        "note": (
            "LTX 2B checkpoint is required. t5xxl_fp8_e4m3fn is already on the volume "
            "(shared with Flux) so fp16 is not needed."
        ),
        "downloads": [
            {
                "source": "url",
                "url": "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors",
                "dest": "checkpoints",
                "filename": "ltx-video-2b-v0.9.5.safetensors",
                "size_mb_approx": 4800,
            },
        ],
        "example_powershell": (
            "$b = @{ input = @{ command = 'download'; downloads = @(@{"
            "source='url'; url='https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors'; "
            "dest='checkpoints'; filename='ltx-video-2b-v0.9.5.safetensors' }) } } | ConvertTo-Json -Depth 10; "
            "Invoke-RestMethod -Uri \"https://api.runpod.ai/v2/$env:RUNPOD_ENDPOINT_ID/run\" -Method POST "
            "-Headers @{ Authorization = \"Bearer $env:RUNPOD_API_KEY\"; 'Content-Type'='application/json' } -Body $b"
        ),
    })
