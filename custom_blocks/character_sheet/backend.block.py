"""Character Sheet — wide multi-view turnaround sheet.

Thin wrapper around ``backend.m_routes.build_character_sheet_workflow``.
Same JSON output as the mobile ``/api/m/character_sheet`` route.
Default canvas is 2048x1024 (wide) so a single sheet fits front / side /
3-quarter views — tweak in the desktop block if you need a 3-row layout.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, services
from backend.m_routes import NEGATIVE_DEFAULT, build_character_sheet_workflow

router = APIRouter()


@router.post("/run")
async def run(request: Request) -> JSONResponse:
    payload = await request.json()
    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id is required"}, status_code=400)

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt is required"}, status_code=400)

    seed_in = payload.get("seed")
    seed_mode = str(payload.get("seed_mode") or "random")
    if seed_mode == "random" or seed_in is None:
        import random
        seed: int | None = random.randint(0, 2**31 - 1)
    else:
        seed = int(seed_in)

    width = int(payload.get("width") or 2048)
    height = int(payload.get("height") or 1024)
    steps = int(payload.get("steps") or 30)
    workflow = build_character_sheet_workflow(
        prompt=prompt,
        width=width,
        height=height,
        steps=steps,
        cfg=float(payload.get("cfg") or 7.0),
        seed=seed,
        negative=str(payload.get("negative") or NEGATIVE_DEFAULT),
        loras=payload.get("loras") or [],
        sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
        scheduler=str(payload.get("scheduler") or "karras"),
    )

    try:
        remote_job_id = services._submit_job(endpoint_id, {"workflow": workflow, "timeout": 600})
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
