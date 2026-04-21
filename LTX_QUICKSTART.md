# LTX Video — Quickstart (BlockFlow)

**TL;DR:** LTX 0.9.5 is Lightricks' fast/cheap video diffusion model. On RunPod Serverless it runs **~4–6× cheaper than Wan 2.2 I2V** for equivalent length clips, because it's a 2B-parameter model vs. Wan's 14B, and it samples in far fewer steps.

- Endpoint route (mobile + desktop tools card): `POST /api/m/ltx_video`
- Info / DL payload: `GET /api/m/ltx_dl_info`
- UI: `/tools` → **LTX Video** card (orange)

## 1. Prerequisite: download models on RunPod (one-time)

LTX needs two files on the RunPod network volume:

| File | Size | Dest |
|---|---|---|
| `ltx-video-2b-v0.9.5.safetensors` | ~4.8 GB | `diffusion_models/` |
| `t5xxl_fp16.safetensors` | ~9.8 GB | `text_encoders/` |

Hit `GET /api/m/ltx_dl_info` to get the ready-to-paste PowerShell snippet — it uses the `comfy-gen download` job handler to pull both into the network volume.

```powershell
# Example (the endpoint returns the exact commands)
comfy-gen download --endpoint-id xio27s12llqzpa `
  --source url --url 'https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors' `
  --dest diffusion_models --filename ltx-video-2b-v0.9.5.safetensors
```

Verify via `list_models` once it finishes — both files should appear.

## 2. Generate — T2V vs I2V

Both modes use the same endpoint. I2V is auto-selected when `image_url` is set.

```http
POST /api/m/ltx_video
Content-Type: application/json

{
  "prompt": "a cat walking in a neon-lit alley, cinematic",
  "image_url": "",               // blank -> T2V, else -> I2V
  "width": 768, "height": 512,
  "length": 97, "fps": 25, "steps": 30
}
```

- `length` must be `8n + 1` (25, 33, 41, …, 97, 105, 121, 161).
- Width/height must be divisible by 32.
- `steps: 30` is a good default; 20 is faster but quality drops.

## 3. UI presets (`/tools` LTX card)

Four shot-based presets fill resolution/length/fps/steps and append a style hint to your prompt:

| Preset | Ratio | Res | Frames | Intended use |
|---|---|---|---|---|
| **Dance (portrait)** | 9:16 | 512×768 | 97 | Full-body dance clips (the project's main use case). Uses the required "standing, full body, facing viewer, arms at sides" hint per [feedback_dance_shot.md](feedback_dance_shot.md). |
| **Close-up** | 1:1 | 768×768 | 65 | Portrait/face. Subtle motion only. |
| **Wide shot** | 16:9 | 1024×576 | 97 | Establishing / landscape. |
| **Cinematic** | ~2.35:1 | 960×544 | 121 | Film-look, anamorphic, longer clip. |

Click a preset first, then edit the prompt — the style hint is appended only if missing, so you can press it multiple times safely.

## 4. Cost comparison (empirical baseline)

| Model | Typical RunPod cost per 97-frame 768×512 clip |
|---|---|
| Wan 2.2 I2V 14B fp8 | ~$0.25–$0.40 |
| LTX 0.9.5 2B         | ~$0.05–$0.08 |

This is why LTX is the recommended first pass for exploration / batching — generate 10 LTX drafts for the cost of 2 Wan clips, then upres the winners with Wan if needed.

## 5. Known limits

- **Motion coherence** on long clips (>121 frames) degrades vs. Wan.
- **Anime style** is weaker than Wan 2.2 Fun Control. For anime dance, prefer Wan with Fun Control pose conditioning and use LTX for realistic clips.
- **NSFW** not well-tuned out of the box; plan on a fine-tune or accept weaker adherence.

## 6. Mock mode

With `BLOCKFLOW_MOCK_RUNPOD=1`, `/api/m/ltx_video` returns a canned job id + placeholder URL without hitting RunPod. Lets you smoke-test the UI flow on the staging tunnel without burning GPU credits.

## 7. Roadmap

- [ ] Replace T5 XXL fp16 with fp8 (half the VRAM, marginal quality cost)
- [ ] Expose `cfg`, `shift` overrides in the UI
- [ ] Batch mode (queue N prompts with per-preset defaults)
- [ ] Auto-upscale winners via Wan I2V refinement pass
