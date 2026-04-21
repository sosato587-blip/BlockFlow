"""Base-model selector: static taxonomy + checkpoint roster.

This block has no RunPod interaction — it surfaces the curated list in
`backend.base_models` plus live LoRA-count metadata so the UI can show
"3 LoRAs under Illustrious, 0 under Flux" etc.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend import services, base_models

router = APIRouter()


@router.get("/families")
def get_families() -> JSONResponse:
    """Return the full family list + counts derived from the current LoRA cache."""
    loras, error, from_cache = services._get_loras(refresh=False)
    grouped_high = base_models.group_loras_by_family(loras.get("high", []))
    grouped_low = base_models.group_loras_by_family(loras.get("low", []))
    resp: dict[str, Any] = {
        "ok": True,
        "families": base_models.family_summary(grouped_high, grouped_low),
        "from_cache": from_cache,
    }
    if error:
        resp["warning"] = error
    return JSONResponse(resp)
