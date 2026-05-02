"""ControlNet (Canny) — composition-controlled SDXL generation.

Thin wrapper around ``backend.m_routes.build_illustrious_controlnet_canny_workflow``.
Same JSON output as the mobile ``/api/m/generate_controlnet`` route.
Only Canny is wired right now (matches mobile constraint).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, services
from backend.m_routes import (
    NEGATIVE_DEFAULT,
    build_illustrious_controlnet_canny_workflow,
)

router = APIRouter()


@router.post("/run")
async def run(request: Request) -> JSONResponse:
    payload = await request.json()
    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id is required"}, status_code=400)

    reference_url = str(payload.get("reference_image_url") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not reference_url:
        return JSONResponse({"ok": False, "error": "reference_image_url is required"}, status_code=400)
    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt is required"}, status_code=400)

    cn_type = str(payload.get("controlnet_type") or "canny").lower()
    if cn_type != "canny":
        return JSONResponse(
            {"ok": False, "error": f"unsupported controlnet_type: {cn_type} (only 'canny' for now)"},
            status_code=400,
        )

    seed_in = payload.get("seed")
    seed_mode = str(payload.get("seed_mode") or "random")
    if seed_mode == "random" or seed_in is None:
        import random
        seed: int | None = random.randint(0, 2**31 - 1)
    else:
        seed = int(seed_in)

    controlnet_model = str(payload.get("controlnet_model") or "diffusers_xl_canny_full.safetensors").strip()
    reference_filename = "controlnet_ref.png"
    workflow = build_illustrious_controlnet_canny_workflow(
        prompt=prompt,
        reference_filename=reference_filename,
        controlnet_model=controlnet_model,
        controlnet_strength=float(payload.get("controlnet_strength") or 0.7),
        width=int(payload.get("width") or 1024),
        height=int(payload.get("height") or 1536),
        steps=int(payload.get("steps") or 30),
        cfg=float(payload.get("cfg") or 7.0),
        seed=seed,
        negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
        loras=payload.get("loras") or [],
        sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
        scheduler=str(payload.get("scheduler") or "karras"),
        canny_low=int(payload.get("canny_low") or 100),
        canny_high=int(payload.get("canny_high") or 200),
    )

    file_inputs: dict[str, Any] = {
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
        if "controlnet" in err_str.lower() or "ControlNetLoader" in err_str:
            return JSONResponse({
                "ok": False,
                "error": (
                    f"ControlNet model '{controlnet_model}' not found on volume. "
                    "See /api/m/controlnet_dl_info for download instructions."
                ),
                "detail": err_str,
            }, status_code=424)
        return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

    return JSONResponse({
        "ok": True,
        "remote_job_id": remote_job_id,
        "endpoint_id": endpoint_id,
        "seed": seed,
        "submitted_at": int(time.time()),
    })


@router.get("/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = services._job_snapshot(job_id)
    if not job:
        return JSONResponse({"job": {"job_id": job_id, "status": "UNKNOWN"}})
    return JSONResponse({"job": job})
