"""ADetailer — auto-fix faces (and optionally hands) on an existing image.

Thin wrapper around ``backend.m_routes.build_illustrious_face_detailer_workflow``.
Same JSON output as the mobile ``/api/m/adetailer`` route.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import config, services
from backend.m_routes import build_illustrious_face_detailer_workflow

router = APIRouter()


@router.post("/run")
async def run(request: Request) -> JSONResponse:
    payload = await request.json()
    endpoint_id = str(payload.get("endpoint_id") or config.RUNPOD_ENDPOINT_ID or "").strip()
    if not endpoint_id:
        return JSONResponse({"ok": False, "error": "endpoint_id is required"}, status_code=400)

    image_url = str(payload.get("image_url") or "").strip()
    if not image_url:
        return JSONResponse({"ok": False, "error": "image_url is required"}, status_code=400)

    seed_in = payload.get("seed")
    seed_mode = str(payload.get("seed_mode") or "random")
    if seed_mode == "random" or seed_in is None:
        import random
        seed: int | None = random.randint(0, 2**31 - 1)
    else:
        seed = int(seed_in)

    image_filename = "adetailer_src.png"
    workflow = build_illustrious_face_detailer_workflow(
        image_filename=image_filename,
        face_prompt=str(
            payload.get("face_prompt")
            or "beautiful face, detailed eyes, sharp focus, high quality, natural skin"
        ),
        face_negative=str(
            payload.get("face_negative")
            or "blurry, deformed, bad anatomy, extra eyes, lowres"
        ),
        bbox_model=str(payload.get("bbox_model") or "bbox/face_yolov8m.pt"),
        sam_model=str(payload.get("sam_model") or "sam_vit_b_01ec64.pth"),
        use_sam=bool(payload.get("use_sam", True)),
        denoise=float(payload.get("denoise") or 0.4),
        steps=int(payload.get("steps") or 20),
        cfg=float(payload.get("cfg") or 7.0),
        seed=seed,
        loras=payload.get("loras") or [],
        sampler_name=str(payload.get("sampler_name") or "dpmpp_2m_sde"),
        scheduler=str(payload.get("scheduler") or "karras"),
        guide_size=int(payload.get("guide_size") or 512),
        feather=int(payload.get("feather") or 5),
    )

    file_inputs: dict[str, Any] = {
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
                "error": (
                    "ADetailer node (Impact Pack) or model missing. "
                    "See /api/m/adetailer_dl_info for install instructions."
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
