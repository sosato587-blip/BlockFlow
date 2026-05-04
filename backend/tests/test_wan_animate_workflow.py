"""Pytest fixtures pinning ``build_wan_animate_workflow``'s output shape.

The builder loads ``custom_blocks/wan_animate/workflow_template.json``
(33-node Kijai WanVideoWrapper API workflow, generated from the
upstream canvas) and patches in user values at well-known node ids.
These tests verify:

  1. The template is reachable at the expected path.
  2. Every well-known node id from ``_WAN_ANIMATE_NODE_IDS`` exists in
     the template with the expected ``class_type``. If a future
     template regeneration shifts the ids, the test fails fast rather
     than silently mis-patching at runtime.
  3. User-provided values land on the right inputs (image / video
     filename, prompt, dimensions, frames, fps, sampler params).
  4. Default acceleration LoRAs (relight + lightx2v) sit in slots 0
     and 1; user picks land in slots 2-4. ``keep_default_acceleration_loras=False``
     wipes everything and starts from slot 0.
  5. Concatenation of ``high_loras`` + ``low_loras`` (Wan Animate is
     single-pass; both branches share the chain).
  6. ``seed=None`` produces a deterministic-shape but fresh value.
"""

from __future__ import annotations

import pytest

from backend.m_routes import (
    WAN_ANIMATE_NEGATIVE_DEFAULT,
    _WAN_ANIMATE_NODE_IDS,
    build_wan_animate_workflow,
    _load_wan_animate_template,
)


EXPECTED_CLASS_TYPES = {
    "model_loader": "WanVideoModelLoader",
    "sampler": "WanVideoSampler",
    "decode": "WanVideoDecode",
    "vae_loader": "WanVideoVAELoader",
    "ref_image": "LoadImage",
    "animate_embeds": "WanVideoAnimateEmbeds",
    "driving_video": "VHS_LoadVideo",
    "text_encode": "WanVideoTextEncodeCached",
    "clip_vision_loader": "CLIPVisionLoader",
    "context_options": "WanVideoContextOptions",
    "video_combine_main": "VHS_VideoCombine",
    "lora_select": "WanVideoLoraSelectMulti",
}


@pytest.fixture
def template():
    return _load_wan_animate_template()


# ---------------------------------------------------------------------------
# 1-2. Template reachable + well-known ids point at correct class_type
# ---------------------------------------------------------------------------


def test_template_reachable(template) -> None:
    assert isinstance(template, dict)
    assert len(template) >= 30, f"template should have ~33 active nodes, got {len(template)}"


@pytest.mark.parametrize("role,expected", sorted(EXPECTED_CLASS_TYPES.items()))
def test_well_known_node_ids_match_class_types(template, role, expected) -> None:
    nid = _WAN_ANIMATE_NODE_IDS[role]
    assert nid in template, f"node id {nid} ({role}) missing from template"
    actual = template[nid]["class_type"]
    assert actual == expected, (
        f"role {role!r}: node {nid} is {actual}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# 3. User values land on the right inputs
# ---------------------------------------------------------------------------


def test_image_and_video_filenames_are_patched() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="my_ref.png", video_filename="my_drive.mp4",
    )
    assert wf["57"]["inputs"]["image"] == "my_ref.png"
    assert wf["63"]["inputs"]["video"] == "my_drive.mp4"


def test_prompt_overrides_default_negative_kept() -> None:
    wf = build_wan_animate_workflow(
        prompt="hello world", image_filename="r.jpg", video_filename="d.mp4",
    )
    assert wf["65"]["inputs"]["positive_prompt"] == "hello world"
    assert wf["65"]["inputs"]["negative_prompt"] == WAN_ANIMATE_NEGATIVE_DEFAULT


def test_explicit_negative_overrides_default() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d", negative="custom neg",
    )
    assert wf["65"]["inputs"]["negative_prompt"] == "custom neg"


def test_dimensions_and_frames_are_patched() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        width=720, height=1280, num_frames=121, fps=24, frame_window_size=49,
    )
    embeds = wf["62"]["inputs"]
    assert embeds["width"] == 720
    assert embeds["height"] == 1280
    assert embeds["num_frames"] == 121
    assert embeds["frame_window_size"] == 49
    # Driving-video resolution should match output dims so motion frames
    # don't need silent rescaling at the WanAnimateEmbeds boundary.
    assert wf["63"]["inputs"]["custom_width"] == 720
    assert wf["63"]["inputs"]["custom_height"] == 1280
    assert wf["63"]["inputs"]["force_rate"] == 24
    # VHS_VideoCombine output frame rate also tracks the user's fps.
    assert wf["30"]["inputs"]["frame_rate"] == 24


def test_sampler_params_are_patched() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        steps=20, cfg=7.5, shift=8.0, seed=42, scheduler="unipc",
        denoise_strength=0.85,
    )
    s = wf["27"]["inputs"]
    assert s["steps"] == 20
    assert s["cfg"] == 7.5
    assert s["shift"] == 8.0
    assert s["seed"] == 42
    assert s["scheduler"] == "unipc"
    assert s["denoise_strength"] == 0.85


def test_seed_none_produces_fresh_int() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d", seed=None,
    )
    seed = wf["27"]["inputs"]["seed"]
    assert isinstance(seed, int)
    assert 0 <= seed < 2**31


def test_filename_prefix_is_patched() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        filename_prefix="MyTake",
    )
    assert wf["30"]["inputs"]["filename_prefix"] == "MyTake"


# ---------------------------------------------------------------------------
# 4-5. LoRA chain
# ---------------------------------------------------------------------------


def test_default_acceleration_loras_kept_in_slots_0_1() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
    )
    loras = wf["171"]["inputs"]
    assert "WanAnimate_relight" in loras["lora_0"]
    assert loras["strength_0"] == 1
    assert "lightx2v" in loras["lora_1"]
    assert loras["strength_1"] == 1.2
    assert loras["lora_2"] == "none"


def test_user_loras_land_in_slots_2_onwards() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        high_loras=[{"name": "char_a.safetensors", "strength": 0.9}],
        low_loras=[{"name": "style_b.safetensors", "strength": 0.6}],
    )
    loras = wf["171"]["inputs"]
    # Defaults preserved
    assert "WanAnimate_relight" in loras["lora_0"]
    assert "lightx2v" in loras["lora_1"]
    # User picks concatenated (Wan Animate is single-pass)
    assert loras["lora_2"] == "char_a.safetensors"
    assert loras["strength_2"] == 0.9
    assert loras["lora_3"] == "style_b.safetensors"
    assert loras["strength_3"] == 0.6
    assert loras["lora_4"] == "none"


def test_user_loras_high_low_concatenated_in_order() -> None:
    """Wan Animate single-pass -> high_loras come before low_loras."""
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        high_loras=[{"name": "h1", "strength": 1.0}, {"name": "h2", "strength": 0.5}],
        low_loras=[{"name": "l1", "strength": 0.7}],
    )
    loras = wf["171"]["inputs"]
    # slots 2, 3, 4 = h1, h2, l1
    assert loras["lora_2"] == "h1"
    assert loras["lora_3"] == "h2"
    assert loras["lora_4"] == "l1"


def test_loras_beyond_slot_4_are_dropped() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        high_loras=[{"name": f"l{i}", "strength": 1.0} for i in range(10)],
    )
    loras = wf["171"]["inputs"]
    # Slots 2, 3, 4 filled; rest dropped silently
    assert loras["lora_2"] == "l0"
    assert loras["lora_3"] == "l1"
    assert loras["lora_4"] == "l2"


def test_none_named_picks_skipped() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        high_loras=[
            {"name": "__none__", "strength": 1.0},  # placeholder from UI
            {"name": "real.safetensors", "strength": 0.8},
        ],
    )
    loras = wf["171"]["inputs"]
    assert loras["lora_2"] == "real.safetensors"
    assert loras["strength_2"] == 0.8


def test_keep_default_false_wipes_acceleration_loras() -> None:
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
        keep_default_acceleration_loras=False,
        high_loras=[{"name": "only.safetensors", "strength": 1.1}],
    )
    loras = wf["171"]["inputs"]
    # User pick now in slot 0
    assert loras["lora_0"] == "only.safetensors"
    assert loras["strength_0"] == 1.1
    assert loras["lora_1"] == "none"


# ---------------------------------------------------------------------------
# 6. Idempotency / no template mutation
# ---------------------------------------------------------------------------


def test_builder_does_not_mutate_disk_template() -> None:
    """Two consecutive calls with different inputs must not bleed into each other."""
    a = build_wan_animate_workflow(
        prompt="alpha", image_filename="a.jpg", video_filename="a.mp4", seed=1,
    )
    b = build_wan_animate_workflow(
        prompt="beta", image_filename="b.jpg", video_filename="b.mp4", seed=2,
    )
    assert a["65"]["inputs"]["positive_prompt"] == "alpha"
    assert b["65"]["inputs"]["positive_prompt"] == "beta"
    assert a["57"]["inputs"]["image"] == "a.jpg"
    assert b["57"]["inputs"]["image"] == "b.jpg"


def test_link_references_unchanged_after_patching() -> None:
    """Patching widget values should never disturb the link references that
    glue the graph together (e.g. WanVideoSampler.model still points at
    node 50, not at a freshly-substituted scalar)."""
    wf = build_wan_animate_workflow(
        prompt="x", image_filename="r", video_filename="d",
    )
    # WanVideoSampler keeps its model / image_embeds / text_embeds links
    assert wf["27"]["inputs"]["model"] == ["50", 0]
    assert wf["27"]["inputs"]["image_embeds"] == ["62", 0]
    assert wf["27"]["inputs"]["text_embeds"] == ["65", 0]
    # WanVideoAnimateEmbeds keeps its vae / clip / pose / mask links
    assert wf["62"]["inputs"]["vae"] == ["38", 0]
    assert wf["62"]["inputs"]["clip_embeds"] == ["70", 0]
