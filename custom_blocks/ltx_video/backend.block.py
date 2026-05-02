"""LTX Video — fast / cheap video generation block (T2V or I2V).

Thin wrapper around ``backend.m_routes.build_ltx_video_workflow``. Same
workflow patcher backs both this desktop block and the existing mobile
``/tools`` LTX card, so JSON output is identical.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, services
from backend.m_routes import build_ltx_video_workflow

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

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt is required"}, status_code=400)

    # I2V vs T2V: image_url is optional. If present, the worker downloads
    # the file and feeds it into LTXVImgToVideo (node 25). If absent, the
    # workflow falls back to the EmptyLTXVLatentVideo T2V path.
    image_url = str(payload.get("image_url") or "").strip()

    seed_in = payload.get("seed")
    seed_mode = str(payload.get("seed_mode") or "random")
    if seed_mode == "random" or seed_in is None:
        import random
        seed = random.randint(0, 2**31 - 1)
    else:
        seed = int(seed_in)

    width = int(payload.get("width") or 768)
    height = int(payload.get("height") or 512)
    length = int(payload.get("length") or 97)
    fps = int(payload.get("fps") or 25)
    steps = int(payload.get("steps") or 30)
    cfg = float(payload.get("cfg") or 3.0)
    negative = str(payload.get("negative") or "low quality, blurry, distorted, static, no movement")

    image_filename = "ltx_src.png" if image_url else None
    workflow = build_ltx_video_workflow(
        prompt=prompt, image_filename=image_filename,
        width=width, height=height, length=length, fps=fps,
        steps=steps, cfg=cfg, seed=seed, negative=negative,
    )

    file_inputs: dict[str, Any] | None = None
    if image_url:
        file_inputs = {"25": {"url": image_url, "filename": image_filename, "field": "image"}}

    job_input: dict[str, Any] = {"workflow": workflow, "timeout": 900}
    if file_inputs:
        job_input["file_inputs"] = file_inputs

    try:
        remote_job_id = services._submit_job(endpoint_id, job_input)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"submit failed: {e}"}, status_code=502)

    return JSONResponse({
        "ok": True,
        "remote_job_id": remote_job_id,
        "endpoint_id": endpoint_id,
        "seed": seed,
        "mode": "i2v" if image_url else "t2v",
        "submitted_at": int(time.time()),
    })


@router.get("/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = services._job_snapshot(job_id)
    if not job:
        return JSONResponse({"job": {"job_id": job_id, "status": "UNKNOWN"}})
    return JSONResponse({"job": job})
