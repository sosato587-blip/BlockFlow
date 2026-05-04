"""A4 — backend integration tests for the high_loras / low_loras payload.

Covers three concerns:

  1. ``_split_loras_from_payload`` — the request-side helper that maps
     either the new split shape or the legacy flat ``loras`` field into
     a ``(high, low)`` tuple, while emitting a one-line deprecation
     warning on the legacy path.

  2. Single-pass parity (``z_image`` + ``illustrious``) — the workflow
     JSON produced by ``loras=[A, B]`` must be byte-identical to the
     JSON produced by ``high_loras=[A], low_loras=[B]`` (and to any
     other allocation that ends up with the same ordered concat). This
     is the AC for Task 7.

  3. Wan I2V dual-pass smoke test — the new ``high_loras`` / ``low_loras``
     params on ``build_wan_i2v_workflow`` must wire ``LoraLoaderModelOnly``
     chains between the two ``UNETLoader`` -> ``ModelSamplingSD3`` legs
     without disturbing the rest of the graph. This is the AC for Task 8.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

import pytest

from backend.m_routes import (
    _split_loras_from_payload,
    build_illustrious_workflow,
    build_wan_i2v_workflow,
    build_z_image_workflow,
)


# ---------------------------------------------------------------------------
# 1. _split_loras_from_payload
# ---------------------------------------------------------------------------


def _capture_stdout(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = fn()
    return result, buf.getvalue()


def test_split_prefers_new_shape() -> None:
    (h, l), out = _capture_stdout(
        lambda: _split_loras_from_payload(
            {"high_loras": [{"name": "a"}], "low_loras": [{"name": "b"}]}
        )
    )
    assert h == [{"name": "a"}]
    assert l == [{"name": "b"}]
    assert "DEPRECATED" not in out


def test_split_legacy_flat_routes_to_high_with_warning() -> None:
    (h, l), out = _capture_stdout(
        lambda: _split_loras_from_payload({"loras": [{"name": "x"}]})
    )
    assert h == [{"name": "x"}]
    assert l == []
    assert "DEPRECATED" in out


def test_split_empty_payload_returns_empty_pair() -> None:
    (h, l), out = _capture_stdout(lambda: _split_loras_from_payload({}))
    assert h == []
    assert l == []
    assert "DEPRECATED" not in out


def test_split_explicit_empty_new_shape_does_not_trigger_legacy() -> None:
    """Caller that explicitly passes ``high_loras=[]`` is on the new shape.

    This case is what the mobile UI sends when no LoRAs are picked, and
    we do NOT want to spam the deprecation warning every time.
    """
    (h, l), out = _capture_stdout(
        lambda: _split_loras_from_payload(
            {"high_loras": [], "low_loras": [], "loras": [{"name": "x"}]}
        )
    )
    assert h == []
    assert l == []
    assert "DEPRECATED" not in out


def test_split_only_high_loras_supplied() -> None:
    (h, l), _ = _capture_stdout(
        lambda: _split_loras_from_payload({"high_loras": [{"name": "a"}]})
    )
    assert h == [{"name": "a"}]
    assert l == []


# ---------------------------------------------------------------------------
# 2. Single-pass parity (z_image + illustrious)
# ---------------------------------------------------------------------------


PICKS = [
    {"name": "a.safetensors", "strength": 0.8},
    {"name": "b.safetensors", "strength": 1.2},
]


@pytest.mark.parametrize(
    "builder,kwargs",
    [
        (build_z_image_workflow, {"prompt": "hi", "seed": 42}),
        (build_illustrious_workflow, {"prompt": "hi", "seed": 42}),
    ],
)
def test_single_pass_legacy_equals_new_shape(builder, kwargs) -> None:
    legacy = builder(loras=PICKS, **kwargs)
    split_high = builder(high_loras=PICKS, **kwargs)
    split_low = builder(low_loras=PICKS, **kwargs)
    split_mix = builder(high_loras=[PICKS[0]], low_loras=[PICKS[1]], **kwargs)
    assert legacy == split_high
    assert legacy == split_low
    assert legacy == split_mix


@pytest.mark.parametrize("builder", [build_z_image_workflow, build_illustrious_workflow])
def test_single_pass_no_loras_path(builder) -> None:
    none_call = builder(prompt="hi", seed=42)
    explicit_empty = builder(prompt="hi", seed=42, high_loras=[], low_loras=[])
    legacy_empty = builder(prompt="hi", seed=42, loras=[])
    assert none_call == explicit_empty == legacy_empty


@pytest.mark.parametrize("builder", [build_z_image_workflow, build_illustrious_workflow])
def test_single_pass_new_shape_overrides_legacy(builder) -> None:
    """If the caller passes both, the new shape wins (legacy is fallback only)."""
    baseline_empty = builder(prompt="hi", seed=42)
    overridden = builder(prompt="hi", seed=42, loras=PICKS, high_loras=[], low_loras=[])
    assert baseline_empty == overridden


# ---------------------------------------------------------------------------
# 3. Wan I2V dual-pass smoke test
# ---------------------------------------------------------------------------


def test_wan_i2v_no_loras_baseline() -> None:
    """With no LoRAs, ModelSamplingSD3 nodes still consume the raw UNETs."""
    wf = build_wan_i2v_workflow(prompt="hi", image_filename="in.png", seed=42)
    assert wf["54"]["inputs"]["model"] == ["37", 0]
    assert wf["55"]["inputs"]["model"] == ["56", 0]
    # No injected loader nodes
    assert not any(k.startswith("370") for k in wf if k != "37")
    assert not any(k.startswith("560") for k in wf if k != "56")


def test_wan_i2v_high_only_chain() -> None:
    wf = build_wan_i2v_workflow(
        prompt="hi", image_filename="in.png", seed=42,
        high_loras=[{"name": "a.safetensors", "strength": 0.8}],
    )
    assert wf["3700"]["class_type"] == "LoraLoaderModelOnly"
    assert wf["3700"]["inputs"]["model"] == ["37", 0]
    assert wf["3700"]["inputs"]["lora_name"] == "a.safetensors"
    assert wf["3700"]["inputs"]["strength_model"] == 0.8
    assert wf["3700"]["_meta"]["title"] == "High Noise LoRA"
    # ModelSamplingSD3 hi now reads from the chain tail
    assert wf["54"]["inputs"]["model"] == ["3700", 0]
    # Low side untouched
    assert wf["55"]["inputs"]["model"] == ["56", 0]


def test_wan_i2v_low_only_chain() -> None:
    wf = build_wan_i2v_workflow(
        prompt="hi", image_filename="in.png", seed=42,
        low_loras=[{"name": "b.safetensors", "strength": 1.2}],
    )
    assert wf["5600"]["class_type"] == "LoraLoaderModelOnly"
    assert wf["5600"]["inputs"]["model"] == ["56", 0]
    assert wf["5600"]["_meta"]["title"] == "Low Noise LoRA"
    assert wf["55"]["inputs"]["model"] == ["5600", 0]
    # High side untouched
    assert wf["54"]["inputs"]["model"] == ["37", 0]


def test_wan_i2v_dual_pass_multi_pick_chain_order() -> None:
    """Multi-pick chains preserve order: 37 -> 3700 -> 3701 -> 54."""
    wf = build_wan_i2v_workflow(
        prompt="hi", image_filename="in.png", seed=42,
        high_loras=[
            {"name": "a", "strength": 0.5},
            {"name": "b", "strength": 0.7},
        ],
        low_loras=[{"name": "c", "strength": 0.9}],
    )
    assert wf["3700"]["inputs"]["model"] == ["37", 0]
    assert wf["3700"]["inputs"]["lora_name"] == "a"
    assert wf["3701"]["inputs"]["model"] == ["3700", 0]
    assert wf["3701"]["inputs"]["lora_name"] == "b"
    assert wf["54"]["inputs"]["model"] == ["3701", 0]

    assert wf["5600"]["inputs"]["model"] == ["56", 0]
    assert wf["5600"]["inputs"]["lora_name"] == "c"
    assert wf["55"]["inputs"]["model"] == ["5600", 0]


def test_wan_i2v_empty_lists_match_baseline() -> None:
    baseline = build_wan_i2v_workflow(prompt="hi", image_filename="in.png", seed=42)
    explicit_empty = build_wan_i2v_workflow(
        prompt="hi", image_filename="in.png", seed=42,
        high_loras=[], low_loras=[],
    )
    assert baseline == explicit_empty


def test_wan_i2v_strength_default() -> None:
    """strength defaults to 1.0 when omitted from a pick dict."""
    wf = build_wan_i2v_workflow(
        prompt="hi", image_filename="in.png", seed=42,
        high_loras=[{"name": "a"}],
    )
    assert wf["3700"]["inputs"]["strength_model"] == 1.0
