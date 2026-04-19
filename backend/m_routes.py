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

import time
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


def build_z_image_workflow(
    prompt: str,
    width: int = 1080,
    height: int = 1920,
    steps: int = 8,
    cfg: float = 1.0,
    seed: int | None = None,
    loras: list[dict[str, Any]] | None = None,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    negative: str = "",
) -> dict[str, Any]:
    """Z-Image Turbo workflow (CLIPLoader + qwen_3_4b + ae VAE)."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

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
) -> dict[str, Any]:
    """Wan 2.2 I2V workflow (high_noise + low_noise 2-pass with ModelSamplingSD3).

    NOTE: Requires file_inputs to be passed alongside this workflow so the
    handler can download the input image into image_filename before execution.
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    return {
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


def build_illustrious_workflow(
    prompt: str,
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
    """Illustrious XL workflow (SDXL family, CheckpointLoaderSimple)."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

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
    loras = payload.get("loras") or []

    file_inputs: dict[str, Any] = {}

    if model == "z_image":
        steps = int(payload.get("steps") or 8)
        cfg = float(payload.get("cfg") or 1.0)
        sampler_name = str(payload.get("sampler_name") or "euler")
        scheduler = str(payload.get("scheduler") or "simple")
        negative = str(payload.get("negative") or "")
        workflow = build_z_image_workflow(
            prompt=prompt, width=width, height=height,
            steps=steps, cfg=cfg, seed=seed, loras=loras,
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
            negative=negative, loras=loras,
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
        )
        file_inputs = {
            "52": {
                "url": image_url,
                "filename": image_filename,
                "field": "image",
            }
        }
    else:
        return JSONResponse(
            {"ok": False, "error": f"unsupported model: {model} (use 'z_image', 'illustrious', or 'wan_i2v')"},
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

        url = f"{config.RUNPOD_API_BASE}/{eid}/status/{remote_job_id}"
        try:
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
        loras = params.get("loras") or []

        if model == "z_image":
            workflow = build_z_image_workflow(
                prompt=prompt, width=width, height=height,
                steps=int(params.get("steps") or 8),
                cfg=float(params.get("cfg") or 1.0),
                seed=int(seed), loras=loras,
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
                loras=loras,
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
    """Upload a base64-encoded image to tmpfiles.org and return public URL.

    Body: { "data": "data:image/png;base64,iVBOR...", "filename": "mask.png" (optional) }
    Returns: { "ok": true, "url": "https://tmpfiles.org/dl/..." }
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

        if len(blob) < 64 or len(blob) > 20 * 1024 * 1024:
            return JSONResponse({"ok": False, "error": f"blob size out of range ({len(blob)} bytes)"}, status_code=400)

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
                "dl_cmd": f'curl -X POST "https://api.runpod.ai/v2/{endpoint_id}/run" -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" -d \'{{"input":{{"command":"download","source":"url","url":"https://huggingface.co/diffusers/controlnet-canny-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors","dest":"controlnet","filename":"diffusers_xl_canny_full.safetensors"}}}}\'',
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
        url = f"{config.RUNPOD_API_BASE}/{eid}/cancel/{remote_job_id}"
        try:
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
