"""Wan 2.2 Animate (Kijai) — block sidecar.

Thin wrapper around ``backend.m_routes.build_wan_animate_workflow`` so the
desktop pipeline block and the mobile ``/api/m/wan_animate`` dispatcher
share one workflow patcher and one set of well-known node ids. The
heavy lifting (canvas-format -> API JSON template, widget-input mapping,
LoRA chain layout) lives in ``m_routes`` and is exercised by 28 pytest
fixtures in ``backend/tests/test_wan_animate_workflow.py``.

POST /run body:
  {
    "endpoint_id": "<runpod>",   // optional, falls back to RUNPOD_ENDPOINT_ID
    "image_url":   "<https://>", // reference still (required)
    "video_url":   "<https://>", // driving video (required)
    "prompt":      "...",
    "negative":    "...",        // optional, defaults to Kijai-stock
    "width": 832, "height": 480,
    "length": 81, "fps": 16,
    "steps": 6, "cfg": 5.0, "shift": 1.0, "scheduler": "dpm++_sde",
    "seed": null,                // null/missing -> random
    "high_loras": [{"name", "strength"}],
    "low_loras":  [{"name", "strength"}],
    "filename_prefix": "WanAnimate"
  }

Response: ``{ok, remote_job_id}`` plus a ``warning`` string when the
caller forgot ``endpoint_id`` and the env var was empty.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, services
from backend.m_routes import build_wan_animate_workflow

router = APIRouter()


@router.post("/run")
async def run(request: Request) -> JSONResponse:
    payload = await request.json()
    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse(
            {"ok": False, "error": "endpoint_id is required (block field or backend .env)"},
            status_code=400,
        )

    image_url = str(payload.get("image_url") or "").strip()
    video_url = str(payload.get("video_url") or "").strip()
    if not image_url:
        return JSONResponse(
            {"ok": False, "error": "image_url (reference still) is required"},
            status_code=400,
        )
    if not video_url:
        return JSONResponse(
            {"ok": False, "error": "video_url (driving video) is required"},
            status_code=400,
        )

    prompt = str(payload.get("prompt") or "")
    negative = payload.get("negative")  # None -> builder default

    seed_in = payload.get("seed")
    seed_mode = str(payload.get("seed_mode") or "random")
    if seed_mode == "random" or seed_in is None:
        import random
        seed = random.randint(0, 2**31 - 1)
    else:
        seed = int(seed_in)

    width = int(payload.get("width") or 832)
    height = int(payload.get("height") or 480)
    num_frames = int(payload.get("length") or payload.get("num_frames") or 81)
    fps = int(payload.get("fps") or 16)
    steps = int(payload.get("steps") or 6)
    cfg = float(payload.get("cfg") or 5.0)
    shift = float(payload.get("shift") or 1.0)
    scheduler = str(payload.get("scheduler") or "dpm++_sde")
    filename_prefix = str(payload.get("filename_prefix") or "WanAnimate")
    keep_default_loras = bool(payload.get("keep_default_acceleration_loras", True))

    high_loras = list(payload.get("high_loras") or [])
    low_loras = list(payload.get("low_loras") or [])
    # Backwards-compat: accept a flat ``loras`` list and route to high.
    if not high_loras and not low_loras:
        legacy = list(payload.get("loras") or [])
        if legacy:
            high_loras = legacy

    image_filename = "wan_animate_ref.png"
    video_filename = "wan_animate_drive.mp4"

    workflow = build_wan_animate_workflow(
        prompt=prompt, image_filename=image_filename, video_filename=video_filename,
        width=width, height=height, num_frames=num_frames, fps=fps,
        steps=steps, cfg=cfg, shift=shift, seed=seed,
        scheduler=scheduler, negative=negative,
        high_loras=high_loras, low_loras=low_loras,
        keep_default_acceleration_loras=keep_default_loras,
        filename_prefix=filename_prefix,
    )

    file_inputs = {
        "57": {"url": image_url, "filename": image_filename, "field": "image"},
        "63": {"url": video_url, "filename": video_filename, "field": "video"},
    }

    job_input: dict[str, Any] = {
        "workflow": workflow,
        "file_inputs": file_inputs,
        "timeout": 900,  # Wan jobs can take 5-10 min cold
    }

    try:
        remote_job_id = services._submit_job(endpoint_id, job_input)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"submit failed: {e}"},
            status_code=502,
        )

    return JSONResponse({
        "ok": True,
        "remote_job_id": remote_job_id,
        "endpoint_id": endpoint_id,
        "seed": seed,
        "submitted_at": int(time.time()),
    })


@router.get("/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    """Mirror of wan_fun_control's status route — returns the cached
    services._job_snapshot for the polling helpers on the frontend."""
    job = services._job_snapshot(job_id)
    if not job:
        return JSONResponse({"job": {"job_id": job_id, "status": "UNKNOWN"}})
    return JSONResponse({"job": job})
