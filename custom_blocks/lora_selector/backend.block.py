from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend import services, base_models

router = APIRouter()


@router.get("/loras")
def get_loras(
    refresh: int = Query(0),
    family: str = Query("", description="Filter to a single base-model family id (e.g. 'illustrious'). Empty = all."),
) -> JSONResponse:
    """Return LoRAs, optionally filtered by base-model family.

    Response shape:
      - `high`, `low`: flat filtered lists (back-compat with existing frontend).
      - `grouped_high`, `grouped_low`: `{family_id: [filename, ...]}` — every
        family key present even if empty.
      - `families`: ordered list of family descriptors with counts + known
        checkpoints (for the Base Model Selector UI).
      - `from_cache`, `warning`: unchanged.
    """
    loras, error, from_cache = services._get_loras(refresh=bool(refresh))
    high_all = loras.get("high", [])
    low_all = loras.get("low", [])

    grouped_high = base_models.group_loras_by_family(high_all)
    grouped_low = base_models.group_loras_by_family(low_all)

    if family:
        if family not in base_models.FAMILIES:
            return JSONResponse(
                {"ok": False, "error": f"unknown family: {family}"},
                status_code=400,
            )
        high_filtered = grouped_high.get(family, [])
        low_filtered = grouped_low.get(family, [])
    else:
        high_filtered = sorted(high_all)
        low_filtered = sorted(low_all)

    resp: dict[str, Any] = {
        "ok": True,
        "high": high_filtered,
        "low": low_filtered,
        "grouped_high": grouped_high,
        "grouped_low": grouped_low,
        "families": base_models.family_summary(grouped_high, grouped_low),
        "from_cache": from_cache,
        "applied_family": family or None,
    }
    if error:
        resp["warning"] = error
    return JSONResponse(resp)


@router.get("/base_models")
def get_base_models() -> JSONResponse:
    """Return base-model families + curated checkpoints.

    This is the 'AI model' dropdown source for the Base Model Selector block.
    Unlike `/loras`, this does NOT hit RunPod — it's a static taxonomy plus
    the LoRA counts derived from the current LoRA cache.
    """
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
