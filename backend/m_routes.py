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

from backend import config, services

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
            "inputs": {"clip": ["2", 0], "text": ""},  # Z-Image works best with empty negative
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
                "sampler_name": "euler",
                "scheduler": "simple",
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
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "karras",
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
        workflow = build_z_image_workflow(
            prompt=prompt, width=width, height=height,
            steps=steps, cfg=cfg, seed=seed, loras=loras,
        )
    elif model == "illustrious":
        steps = int(payload.get("steps") or 30)
        cfg = float(payload.get("cfg") or 7.0)
        negative = str(payload.get("negative") or NEGATIVE_DEFAULT)
        workflow = build_illustrious_workflow(
            prompt=prompt, width=width, height=height,
            steps=steps, cfg=cfg, seed=seed,
            negative=negative, loras=loras,
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

    endpoint_id = config.RUNPOD_ENDPOINT_ID
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "RUNPOD_ENDPOINT_ID not configured"}, status_code=500)

    job_input: dict[str, Any] = {"workflow": workflow}
    if file_inputs:
        job_input["file_inputs"] = file_inputs
        job_input["timeout"] = 900  # Wan jobs can take 5-10 min

    try:
        remote_job_id = services._submit_job(endpoint_id, job_input)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

    return JSONResponse({
        "ok": True,
        "remote_job_id": remote_job_id,
        "endpoint_id": endpoint_id,
        "model": model,
        "submitted_at": time.time(),
    })


@router.get("/api/m/status/{remote_job_id}")
async def m_status(remote_job_id: str) -> JSONResponse:
    """Check status of a RunPod job by its remote id."""
    endpoint_id = config.RUNPOD_ENDPOINT_ID
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "RUNPOD_ENDPOINT_ID not configured"}, status_code=500)

    url = f"{config.RUNPOD_API_BASE}/{endpoint_id}/status/{remote_job_id}"
    try:
        resp = services._request_json("GET", url, None, timeout=config.HTTP_TIMEOUT_SEC)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"status fetch failed: {e}"}, status_code=502)

    return JSONResponse({"ok": True, **resp})


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
