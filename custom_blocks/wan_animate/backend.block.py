"""Wan 2.2 Animate — character animation from reference image + driving video.

⚠️ SCAFFOLDING ONLY (2026-05-02). This module is intentionally empty: it
holds the router stub, the canvas asset has been checked in next door,
and the design analysis lives in ``WAN_ANIMATE_DESIGN.md``. The runtime
path is implemented in a follow-up session — see "Next session" in
``WAN_ANIMATE_DESIGN.md`` for the work list.

Why a stub instead of a partial implementation:
  The Kijai workflow has 66 canvas-format nodes, several Kijai-specific
  custom-node classes, and a non-trivial widget→input mapping. Shipping
  a half-built builder risks burning RunPod credit on workflows that
  only fail at the worker. The follow-up session does the canvas → API
  conversion + builder + dispatcher + UI as one coherent change.

Plan (see WAN_ANIMATE_DESIGN.md § "Next session"):
  1. scripts/convert_canvas_to_api.py  — one-shot canvas → API converter
  2. workflow_template.json            — generated API JSON
  3. build_wan_animate_workflow()      — patcher in m_routes.py
  4. /api/m/wan_animate                 — dispatcher
  5. mobile UI extension               — ModelKind, dropdown, video URL
  6. desktop block frontend            — InlineLoraPicker, sampler, etc.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


# Routes intentionally empty during scaffolding. The block sidecar
# auto-loader picks this file up so the namespace is reserved, but no
# endpoints respond yet. The frontend stub will hide itself from the
# block palette while ``CONFIG_DRAFT`` is True (see frontend.block.tsx).
CONFIG_DRAFT = True
