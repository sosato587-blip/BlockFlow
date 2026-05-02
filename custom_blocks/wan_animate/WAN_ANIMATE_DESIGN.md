# Wan 2.2 Animate — design notes

> **Status (2026-05-02):** scaffolding only. Catalog rows registered, canvas
> JSON checked in as a reference asset. The runtime path (canvas → API
> conversion, programmatic builder, ``/api/m/wan_animate`` dispatcher,
> mobile / desktop UI) is **not implemented yet**. See "Next session" at
> the bottom of this doc.

## What this block does

Kijai's Wan 2.2 Animate flow turns **one reference image + one driving
video** into a video where the reference subject performs the driving
video's motion. Use cases:

- Anime / 3DCG character doing a real dance video's choreography.
- Identity-preserving "talking head" lip-sync from a driving clip.
- Clothing / pose transfer for product visualization.

It's a different beast from Wan I2V (which only takes an image and
imagines motion from text) and from Wan Fun Control (which uses a
control video for pose only, no identity transfer).

## Source

The canonical reference is Kijai's example:

- Repo: <https://github.com/kijai/ComfyUI-WanVideoWrapper>
- Workflow: ``example_workflows/wanvideo_WanAnimate_example_01.json``
- Model: <https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled>

The 136 KB ``workflow_canvas.json`` next to this doc is the raw canvas
JSON pulled from the example as of 2026-05-02. It is the source of
truth for the node graph.

## Required files on the RunPod network volume

All HuggingFace-hosted (no civitai gating). Total ~31 GB.

| Filename | Path | Size | Source |
|---|---|---|---|
| ``Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors`` | ``diffusion_models/`` | ~17 GB | Kijai HF |
| ``umt5-xxl-enc-bf16.safetensors`` | ``text_encoders/`` | ~12 GB | Kijai HF |
| ``Wan2_1_VAE_bf16.safetensors`` | ``vae/`` | ~600 MB | Kijai HF |
| ``WanAnimate_relight_lora_fp16.safetensors`` | ``loras/`` | ~600 MB | Kijai HF |
| ``lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors`` | ``loras/`` | ~1 GB | Kijai HF |
| ``clip_vision_h.safetensors`` | ``clip_vision/`` | ~1.2 GB | already on volume (shared with charaip / wan_i2v) |

The lightx2v LoRA is the speed-distillation acceleration that lets us
run with ``steps=6`` instead of 30. Without it, ``steps`` jumps to 25-30
and per-job cost ~5x.

## Required ComfyUI custom nodes on the worker

Confirmed by `comfy_gen_info_cache.json` parsing of the canvas JSON:

- ``ComfyUI-WanVideoWrapper`` (Kijai) — provides every ``WanVideo*`` class.
- ``ComfyUI-KJNodes`` — ``GetNode`` / ``SetNode`` / ``BlockifyMask`` / ``GrowMask`` / ``ImageResizeKJv2`` / ``PointsEditor`` / ``DrawMaskOnImage`` / ``GetImageSizeAndCount`` / ``FaceMaskFromPoseKeypoints`` / ``PixelPerfectResolution``.
- ``ComfyUI-VideoHelperSuite`` — ``VHS_LoadVideo`` / ``VHS_VideoCombine``.
- ``ComfyUI-WanAnimatePreprocess`` (Kijai) — ``DWPreprocessor`` (pose) and SAM 2 helpers.
- ``ComfyUI-segment-anything-2`` — ``DownloadAndLoadSAM2Model`` / ``Sam2Segmentation``.

## Node inventory (66 total in the canvas)

| Group | Class types | IDs (canvas) |
|---|---|---|
| Model loading | ``WanVideoModelLoader``, ``WanVideoVAELoader``, ``CLIPVisionLoader`` | 22, 38, 71 |
| Text encoding | ``WanVideoTextEncodeCached`` | 65 |
| Inputs | ``LoadImage`` (ref image), ``VHS_LoadVideo`` (driving video) | 57, 63 |
| Pose extraction | ``DWPreprocessor`` | 73 |
| Identity / vision encoding | ``WanVideoClipVisionEncode`` | 70 |
| Animation core | ``WanVideoAnimateEmbeds`` | 62 |
| LoRA chain | ``WanVideoSetLoRAs``, ``WanVideoLoraSelectMulti`` | 48, 171 |
| Optimization | ``WanVideoBlockSwap``, ``WanVideoSetBlockSwap``, ``WanVideoTorchCompileSettings``, ``WanVideoContextOptions`` | 51, 50, 35, 110 |
| Sampling | ``WanVideoSampler`` | 27 |
| SAM 2 mask | ``DownloadAndLoadSAM2Model``, ``Sam2Segmentation``, ``GrowMask``, ``BlockifyMask``, ``FaceMaskFromPoseKeypoints``, ``PointsEditor``, ``DrawMaskOnImage`` | 102, 104, 100, 108, 120, 107, 99 |
| Image processing | ``ImageResizeKJv2``, ``ImageConcatMulti``, ``ImageCropByMaskAndResize``, ``GetImageSizeAndCount``, ``PixelPerfectResolution`` | 64, 66, 77, 96, 42, 152 |
| Decode + output | ``WanVideoDecode``, ``VHS_VideoCombine`` (×3 outputs) | 28, 112, 30, 75 |
| Canvas helpers (skipped at API conversion) | ``GetNode``, ``SetNode``, ``Reroute``, ``INTConstant``, ``Note``, ``MarkdownNote`` | many |

## Default parameter set (extracted from canvas widget values)

```
WanVideoSampler:
  steps=6, cfg=5.0, scheduler="dpm++_sde", shift=1.0, denoise=1.0,
  seed=42, riflex_freq_index=0, force_offload=True, batched_cfg=False
WanVideoAnimateEmbeds:
  width=832, height=480, num_frames=501, frame_window_size=77,
  force_offload=False, colormatch="disabled",
  pose_strength=1.0, face_strength=1.0
VHS_LoadVideo:
  force_rate=16, custom_width=960, custom_height=544,
  frame_load_cap=0, skip_first_frames=0, select_every_nth=1
VHS_VideoCombine (final output):
  frame_rate=16, format="video/h264-mp4", crf=19, pix_fmt="yuv420p"
WanVideoLoraSelectMulti:
  lora_1="WanVideo\WanAnimate_relight_lora_fp16.safetensors", strength_1=1.0
  lora_2="WanVideo\Lightx2v\lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors", strength_2=1.2
WanVideoBlockSwap:
  blocks_to_swap=25
WanVideoModelLoader:
  precision="fp16_fast", quantization="disabled",
  load_device="offload_device", attention_mode="sageattn"
```

## UI parameters to expose (mobile + desktop block)

The full canvas drives 80+ widgets. The ones a user would realistically
want to tune per-job:

- **Required**: ``image_url`` (reference image), ``video_url`` (driving video), ``prompt``, ``negative`` (default Chinese ugly-list).
- **Common**: ``width`` / ``height`` (default 832×480), ``num_frames`` (default 81 for ~5 sec clip @ 16fps).
- **Sampling**: ``steps`` (default 6 — keep low when lightx2v is on), ``cfg`` (default 5.0), ``seed_mode`` (random / fixed), ``seed_value``, ``scheduler`` (default ``dpm++_sde``), ``shift``.
- **Per-LoRA inline picks**: reuse the existing ``<InlineLoraPicker>`` on top of the relight + lightx2v defaults.

Hide behind a "Advanced" section: ``frame_window_size``, ``pose_strength``, ``face_strength``, ``colormatch``, ``blocks_to_swap``, ``force_offload``, ``riflex_freq_index``, SAM 2 mask point editing.

## Cost notes

Calibration target after first three end-to-end runs:

```python
"wan_animate": {"base": 0.18, "per_second": 0.009}  # current placeholder
```

5-sec clip → ~$0.225 estimated. Lightx2v keeps ``steps=6`` so per-job
cost stays close to LTX, much cheaper than wan_i2v's dual-pass ~$0.30.

## Next session — what to implement

1. **Canvas → API converter** (one-shot script under ``scripts/``).
   Resolves ``SetNode`` / ``GetNode`` / ``Reroute`` chains, maps
   ``widgets_values`` (positional) to input names using ``INPUT_TYPES``
   from Kijai's ``nodes.py`` / ``nodes_sampler.py`` / ``nodes_model_loading.py``.
   Output: ``custom_blocks/wan_animate/workflow_template.json`` (API format).

2. **Builder**: ``backend/m_routes.py:build_wan_animate_workflow()``.
   Loads the API template, substitutes ``image_filename``, ``video_filename``,
   ``prompt``, ``negative``, ``width``, ``height``, ``num_frames``, ``steps``,
   ``cfg``, ``shift``, ``seed``, plus high/low LoRA picks at the well-known
   node IDs (22, 27, 28, 30, 38, 57, 62, 63, 65, 71, 73, 110, 171). Pytest
   pins the JSON shape with one fixture for each user-tunable key.

3. **Mobile dispatcher**: ``/api/m/wan_animate`` with a ``file_inputs``
   map for both LoadImage (57) and VHS_LoadVideo (63).

4. **Mobile UI**: extend ``ModelKind`` to include ``wan_animate``,
   add the option to the model dropdown, conditional ``video_url``
   field, ``onModelChange`` defaults (480×832, 81f, 16fps, steps 6,
   cfg 5, dpm++_sde / simple).

5. **Desktop block**:
   - ``custom_blocks/wan_animate/backend.block.py`` — ``/run`` POSTs to
     ``/api/m/wan_animate`` (or builds the workflow inline; choose one).
   - ``custom_blocks/wan_animate/frontend.block.tsx`` — pattern after
     ``custom_blocks/wan_fun_control/frontend.block.tsx`` (image + video
     pickers, prompt, KSampler card, seed mode, LoRA picker, advanced).

6. **End-to-end smoke test**: 1 real generation on endpoint
   ``xio27s12llqzpa`` to verify the pipeline + calibrate the cost rate.
