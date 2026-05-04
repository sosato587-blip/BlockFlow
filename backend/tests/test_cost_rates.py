"""Cost-rate sanity tests.

The video cost table in ``backend.m_store.COST_RATES`` got expanded with
``wan_animate`` / ``wan_fun_control`` / ``ltx_video`` entries. These tests
pin the existing formulas (so refactors don't silently change pricing
that the UI surfaces in cost previews / loop budgets) and assert the new
entries land in plausible bands relative to the calibration data we
have:

  * Wan I2V dual-pass: ~$0.30-0.40 per ~2-sec clip (m_store comment +
    AUTONOMOUS_REPORT_DAY3 confirms 15 video x ~$0.30 = $4.50).
  * LTX 0.9.5 2B: $0.05-0.08 per 97f / 768x512 / 30 step (LTX_QUICKSTART).

Wan Animate is single-pass 14B, so its per-second rate must be lower
than Wan I2V's (and we expect roughly half).
"""

from __future__ import annotations

import pytest

from backend.m_store import COST_RATES, _VIDEO_MODELS, estimate_cost


# ---------------------------------------------------------------------------
# Existing rates — pin formulas so refactors don't change billing surface.
# ---------------------------------------------------------------------------


def test_z_image_formula_unchanged() -> None:
    """1080x1920 at 8 steps = base 0.012 + 2.0736MP * 8 * 0.00018 ~ $0.015."""
    cost = estimate_cost("z_image", width=1080, height=1920, steps=8)
    assert 0.014 < cost < 0.016


def test_illustrious_formula_unchanged() -> None:
    cost = estimate_cost("illustrious", width=1024, height=1536, steps=30)
    assert 0.013 < cost < 0.016


def test_wan_i2v_formula_unchanged() -> None:
    """33f@16fps ~ 2.06 sec -> 0.30 + 2.06 * 0.015 = 0.331."""
    cost = estimate_cost("wan_i2v", length=33, fps=16)
    assert 0.30 < cost < 0.35


# ---------------------------------------------------------------------------
# New rates.
# ---------------------------------------------------------------------------


def test_wan_animate_cheaper_than_wan_i2v_per_second() -> None:
    """Single-pass should beat dual-pass at the same duration."""
    same_duration = {"length": 49, "fps": 16}
    assert estimate_cost("wan_animate", **same_duration) < estimate_cost(
        "wan_i2v", **same_duration
    )


def test_wan_animate_lands_in_expected_band() -> None:
    """49f @ 16fps (~3 sec) should be ~$0.20, not the dual-pass ~$0.35."""
    cost = estimate_cost("wan_animate", length=49, fps=16)
    assert 0.18 < cost < 0.25


def test_wan_fun_control_matches_wan_i2v_for_same_duration() -> None:
    same_duration = {"length": 49, "fps": 16}
    diff = abs(
        estimate_cost("wan_fun_control", **same_duration)
        - estimate_cost("wan_i2v", **same_duration)
    )
    assert diff < 0.001


def test_ltx_video_in_empirical_band() -> None:
    """LTX_QUICKSTART says $0.05-0.08 for a 97f / 768x512 clip @ 25fps."""
    cost = estimate_cost("ltx_video", length=97, fps=25)
    assert 0.05 < cost < 0.10


@pytest.mark.parametrize("model", sorted(_VIDEO_MODELS))
def test_video_models_use_seconds_formula(model: str) -> None:
    """Every model in ``_VIDEO_MODELS`` should use ``base + sec*per_second``."""
    rates = COST_RATES[model]
    assert "base" in rates and "per_second" in rates
    short = estimate_cost(model, length=17, fps=16)   # ~1.06 sec
    long_ = estimate_cost(model, length=97, fps=16)   # ~6.06 sec
    assert long_ > short, f"{model}: longer clip must cost more"


def test_unknown_model_falls_back_to_constant() -> None:
    assert estimate_cost("unknown_model", length=33) == 0.04
