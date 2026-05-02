"""Outpaint — extend canvas around an image.

Thin wrapper around ``backend.m_routes.build_illustrious_outpaint_workflow``.
Same JSON output as the mobile ``/api/m/outpaint`` route.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, services
from backend.m_routes import NEGATIVE_DEFAULT, build_illustrious_outpaint_workflow

router = APIRouter()


@router.post("/run")
async def run(request: Request) -> JSONResponse:
    payload = await request.json()
    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id is required"}, status_code=400)

    image_url = str(payload.get("image_url") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not image_url:
        return JSONResponse({"ok": False, "error": "image_url is required"}, status_code=400)
    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt is required"}, status_code=400)

    seed_in = payload.get("seed")
    seed_mode = str(payload.get("seed_mode") or "random")
    if seed_mode == "random" or seed_in is None:
        import random
        seed: int | None = random.randint(0, 2**31 - 1)
    else:
        seed = int(seed_in)

    image_filename = "outpaint_src.png"
    workflow = build_illustrious_outpaint_workflow(
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
        seed=seed,
        negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
        loras=payload.get("loras") or [],
        sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
        scheduler=str(payload.get("scheduler") or "karras"),
    )

    file_inputs: dict[str, Any] = {
        "50": {"url": image_url, "filename": image_filename, "field": "image"},
    }

    try:
        remote_job_id = services._submit_job(endpoint_id, {
            "workflow": workflow,
            "file_inputs": file_inputs,
            "timeout": 600,
        })
    except Exception as e:
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
