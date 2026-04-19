"""Wan 2.2 Fun Control — dance/motion transfer via ComfyUI workflow on RunPod.

Builds an API-format ComfyUI workflow and sends it to the RunPod serverless
endpoint. Uses 2-pass KSamplerAdvanced (high noise + low noise models) with
Wan22FunControlToVideo node.

Supports two control modes:
- 'real': direct video as control (output follows video appearance)
- 'anime': DWPreprocessor extracts pose skeleton first (preserves character look)
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, state, services


router = APIRouter()


def _build_workflow(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    length: int,
    cfg: float,
    shift: float,
    steps: int,
    seed: int,
    control_mode: str = "real",
) -> dict[str, Any]:
    """Build a ComfyUI API-format workflow for Wan 2.2 Fun Control."""
    half_steps = steps // 2
    wf: dict[str, Any] = {
        # Model loaders
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "fp8_e4m3fn",
            },
        },
        "2": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "fp8_e4m3fn",
            },
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
            },
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
        },
        # Input files (patched by file_inputs)
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": "start_image.png"},
        },
        "11": {
            "class_type": "VHS_LoadVideo",
            "inputs": {
                "video": "control_video.mp4",
                "force_rate": 16,
                "force_size": "Disabled",
                "custom_width": width,
                "custom_height": height,
                "frame_load_cap": length,
                "skip_first_frames": 0,
                "select_every_nth": 1,
                "unique_id": 11,
            },
        },
        # Text prompts
        "20": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["3", 0]},
        },
        "21": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["3", 0]},
        },
        # ModelSamplingSD3
        "30": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"shift": shift, "model": ["1", 0]},
        },
        "31": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"shift": shift, "model": ["2", 0]},
        },
    }

    # Control video source: direct or via DWPreprocessor
    if control_mode == "anime":
        wf["15"] = {
            "class_type": "DWPreprocessor",
            "inputs": {
                "image": ["11", 0],
                "detect_hand": "enable",
                "detect_body": "enable",
                "detect_face": "enable",
                "resolution": 512,
                "bbox_detector": "yolox_l.onnx",
                "pose_estimator": "dw-ll_ucoco_384_bs5.torchscript.pt",
            },
        }
        control_ref = ["15", 0]
    else:
        control_ref = ["11", 0]

    # Wan22FunControlToVideo
    wf["40"] = {
        "class_type": "Wan22FunControlToVideo",
        "inputs": {
            "width": width,
            "height": height,
            "length": length,
            "batch_size": 1,
            "positive": ["20", 0],
            "negative": ["21", 0],
            "vae": ["4", 0],
            "ref_image": ["10", 0],
            "control_video": control_ref,
        },
    }

    # 2-pass sampling
    wf["50"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["30", 0],
            "positive": ["40", 0],
            "negative": ["40", 1],
            "latent_image": ["40", 2],
            "add_noise": "enable",
            "noise_seed": seed,
            "control_after_generate": "fixed",
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": 0,
            "end_at_step": half_steps,
            "return_with_leftover_noise": "enable",
        },
    }
    wf["51"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["31", 0],
            "positive": ["40", 0],
            "negative": ["40", 1],
            "latent_image": ["50", 0],
            "add_noise": "disable",
            "noise_seed": seed,
            "control_after_generate": "fixed",
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": half_steps,
            "end_at_step": 10000,
            "return_with_leftover_noise": "disable",
        },
    }

    # Decode + save
    wf["60"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["51", 0], "vae": ["4", 0]},
    }
    wf["70"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["60", 0],
            "frame_rate": 16,
            "loop_count": 0,
            "filename_prefix": "wan22_fun_control",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
        },
    }

    return wf


@router.post("/run")
async def run(request: Request) -> JSONResponse:
    payload = await request.json()
    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID)
    image_url = str(payload.get("image_url") or "")
    video_url = str(payload.get("video_url") or "")
    prompt = str(payload.get("prompt") or "anime character dancing, smooth motion, high quality")
    negative_prompt = str(payload.get("negative_prompt") or "static, blurry, distorted, bad quality, morphing, deformed, flickering, jittering, face deformation, shifting features, warping")
    control_mode = str(payload.get("control_mode", "real"))
    width = int(payload.get("width", 480))
    height = int(payload.get("height", 832))
    length = int(payload.get("length", 81))
    cfg = float(payload.get("cfg", 1.0))
    shift = float(payload.get("shift", 8.0))
    steps = int(payload.get("steps", 20))
    seed = int(payload.get("seed", 42))
    seed_mode = str(payload.get("seed_mode", "random"))

    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id is required"}, status_code=400)
    if not image_url:
        return JSONResponse({"ok": False, "error": "image_url is required"}, status_code=400)
    if not video_url:
        return JSONResponse({"ok": False, "error": "video_url is required"}, status_code=400)

    if seed_mode == "random":
        import random
        seed = random.randint(0, 2**32 - 1)

    workflow = _build_workflow(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        length=length,
        cfg=cfg,
        shift=shift,
        steps=steps,
        seed=seed,
        control_mode=control_mode,
    )

    file_inputs = {
        "10": {"url": image_url, "filename": "start_image.png", "field": "image"},
        "11": {"url": video_url, "filename": "control_video.mp4", "field": "video"},
    }

    job_input = {
        "workflow": workflow,
        "file_inputs": file_inputs,
        "timeout": 900,
    }

    try:
        job_id = str(uuid.uuid4())
        record = services._new_job_record(job_id, endpoint_id, job_input)
        with state.JOBS_LOCK:
            state.JOBS[job_id] = record
            state._persist_jobs_locked()

        state.EXECUTOR.submit(services._run_local_job, job_id, endpoint_id, job_input)

        return JSONResponse({"ok": True, "job_ids": [job_id]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = services._job_snapshot(job_id)
    if not job:
        return JSONResponse({"job": {"job_id": job_id, "status": "UNKNOWN"}})
    return JSONResponse({"job": job})
