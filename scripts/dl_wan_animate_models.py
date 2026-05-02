"""DL helper for the Wan 2.2 Animate (Kijai) model stack.

Five files, all on HuggingFace, totaling ~32 GB. Goes through the same
pattern as ``scripts/dl_onepiece_loras.py`` (auto-load .env, single
combined RunPod ``input.command="download"`` job, dry-run by default,
``--execute`` confirms before submitting).

Files (HF source -> RunPod ``models/<dest>/<filename>``):

  * Wan Animate 14B fp8 UNet      -> diffusion_models/<file>          (~18.4 GB)
  * umt5 xxl bf16 text encoder    -> text_encoders/<file>             (~11.4 GB)
  * Wan 2.1 VAE bf16              -> vae/<file>                       (~600 MB)
  * WanAnimate relight LoRA       -> loras/<file>                     (~1.4 GB)
  * lightx2v acceleration LoRA    -> loras/<file>                     (~700 MB)

The block + mobile UI both reference these by their flat filenames
(matching the rows in ``backend/base_models.py:KNOWN_CHECKPOINTS`` and
the patcher's expected paths in
``custom_blocks/wan_animate/workflow_template.json``). If the volume
already contains some of them, those entries are reported as ``[skip]``
and dropped from the download payload — no wasted RunPod minutes.

Usage on the mini PC::

    uv run scripts/dl_wan_animate_models.py            # dry run
    uv run scripts/dl_wan_animate_models.py --execute  # really submit

Optional flags:

    --endpoint-id xio27s12llqzpa   override RUNPOD_ENDPOINT_ID for one run
    --skip-loras                   only DL the model + text encoder + VAE
    --skip-acceleration            DL only the relight LoRA, not lightx2v
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_CANDIDATES = [REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"]
CACHE_PATH = REPO_ROOT / "comfy_gen_info_cache.json"


def _load_env_file(path: Path, *, override_empty: bool = True) -> list[str]:
    """Mirror of scripts/dl_onepiece_loras.py:_load_env_file."""
    applied: list[str] = []
    if not path.exists():
        return applied
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        existing = os.environ.get(key)
        already_set = existing is not None and (existing != "" or not override_empty)
        if not already_set:
            os.environ[key] = val
            applied.append(key)
    return applied


_loaded_env_summary: list[tuple[str, list[str]]] = []
for _candidate in ENV_CANDIDATES:
    if _candidate.exists():
        _loaded_env_summary.append((str(_candidate), _load_env_file(_candidate)))


# Each entry = (dest, filename, size_mb, url, role)
TARGETS: list[dict] = [
    {
        "role": "unet",
        "dest": "diffusion_models",
        "filename": "Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors",
        "size_mb": 18400,
        "url": "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors",
    },
    {
        "role": "text_encoder",
        "dest": "text_encoders",
        "filename": "umt5-xxl-enc-bf16.safetensors",
        "size_mb": 11400,
        "url": "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors",
    },
    {
        "role": "vae",
        "dest": "vae",
        "filename": "Wan2_1_VAE_bf16.safetensors",
        "size_mb": 600,
        "url": "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors",
    },
    {
        "role": "lora_relight",
        "dest": "loras",
        "filename": "WanAnimate_relight_lora_fp16.safetensors",
        "size_mb": 1440,
        "url": "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors",
    },
    {
        "role": "lora_lightx2v",
        "dest": "loras",
        "filename": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
        "size_mb": 738,
        "url": "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
    },
]


def load_existing_loras() -> set[str]:
    """LoRA-only existing inventory from the ComfyGen disk cache.

    The cache only tracks ``loras/`` (it's populated by the ComfyGen
    block's Sync, which calls ``list_models`` for that one type). We use
    it for the LoRA dedup check; the diffusion_models / text_encoders /
    vae files are always submitted (the worker already overwrites if
    they exist, so re-running is idempotent enough for our purpose).
    """
    if not CACHE_PATH.exists():
        return set()
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {str(x).lower() for x in (data.get("loras") or []) if isinstance(x, str)}


def diff_targets(plan: list[dict], existing_loras: set[str]) -> tuple[list[dict], list[dict]]:
    """Split into (will_download, will_skip).

    Skips a target only when its dest is ``loras`` AND the filename is
    already in the cached inventory. Other dests always download.
    """
    todo: list[dict] = []
    skip: list[dict] = []
    for t in plan:
        if t["dest"] == "loras" and t["filename"].lower() in existing_loras:
            skip.append(t)
        else:
            todo.append(t)
    return todo, skip


def _runpod_post(endpoint_id: str, api_key: str, body: dict, timeout: int = 30) -> dict:
    req = Request(
        f"https://api.runpod.ai/v2/{endpoint_id}/run",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _runpod_status(endpoint_id: str, api_key: str, job_id: str, timeout: int = 15) -> dict:
    req = Request(
        f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def submit_download_job(
    endpoint_id: str,
    api_key: str,
    downloads: list[dict],
    poll_timeout_sec: float = 1800.0,  # 30 min — 32 GB DL on a slow link
    poll_interval_sec: float = 10.0,
) -> dict:
    submit = _runpod_post(
        endpoint_id, api_key,
        {"input": {"command": "download", "downloads": downloads}},
    )
    job_id = submit.get("id")
    if not job_id:
        raise RuntimeError(f"RunPod submit returned no job id: {submit!r}")
    print(f"job submitted: {job_id}")

    deadline = time.time() + poll_timeout_sec
    last_status = ""
    while time.time() < deadline:
        try:
            resp = _runpod_status(endpoint_id, api_key, job_id)
        except (HTTPError, URLError) as e:
            print(f"  poll error (will retry): {e}")
            time.sleep(poll_interval_sec)
            continue
        status = str(resp.get("status", "")).upper()
        if status != last_status:
            elapsed = int(time.time() - (deadline - poll_timeout_sec))
            print(f"  [{elapsed}s] {status}")
            last_status = status
        if status in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
            return resp
        time.sleep(poll_interval_sec)
    raise TimeoutError(f"job {job_id} did not complete within {poll_timeout_sec}s")


def render_table(plan: list[dict], skip: list[dict]) -> None:
    print()
    print(f"  {'Role':<18}{'Dest':<18}{'Size':>8}  Filename")
    print(f"  {'-'*18}{'-'*18}{'-'*8}  --------")
    for t in plan:
        size = f"{t['size_mb']/1024:.1f} GB" if t["size_mb"] >= 1024 else f"{t['size_mb']} MB"
        print(f"  {'[NEW] ' + t['role']:<18}{t['dest']:<18}{size:>8}  {t['filename']}")
    for t in skip:
        size = f"{t['size_mb']/1024:.1f} GB" if t["size_mb"] >= 1024 else f"{t['size_mb']} MB"
        print(f"  {'[skip] ' + t['role']:<18}{t['dest']:<18}{size:>8}  {t['filename']}")
    print()


def _print_env_diagnostic() -> None:
    if not _loaded_env_summary:
        print("env: no .env file found (looked in repo root and backend/)")
    else:
        for path, keys in _loaded_env_summary:
            if keys:
                print(f"env: loaded from {path} -> {', '.join(sorted(keys))}")
            else:
                print(f"env: {path} exists but every key was already set in the shell")
    for k in ("RUNPOD_API_KEY", "RUNPOD_ENDPOINT_ID"):
        v = os.environ.get(k, "")
        state = "(set)" if v else "(EMPTY)"
        print(f"  {k}: {state}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="Actually submit the RunPod download job. Without this, only print the plan.")
    ap.add_argument("--endpoint-id", default="",
                    help="RunPod endpoint id. Falls back to RUNPOD_ENDPOINT_ID env var.")
    ap.add_argument("--skip-loras", action="store_true",
                    help="Only DL the UNet + text encoder + VAE (skip both LoRAs).")
    ap.add_argument("--skip-acceleration", action="store_true",
                    help="Skip the lightx2v acceleration LoRA (keep relight). "
                         "Use this if you want full-quality 25-30 step renders "
                         "instead of the lightx2v 6-step path.")
    args = ap.parse_args()

    _print_env_diagnostic()
    print()

    plan = list(TARGETS)
    if args.skip_loras:
        plan = [t for t in plan if t["dest"] != "loras"]
    elif args.skip_acceleration:
        plan = [t for t in plan if t["role"] != "lora_lightx2v"]

    existing_loras = load_existing_loras()
    todo, skip = diff_targets(plan, existing_loras)
    render_table(todo, skip)

    if not todo:
        print("All requested targets already present on the volume. Nothing to download.")
        return 0

    total_mb = sum(t["size_mb"] for t in todo)
    total_str = f"{total_mb/1024:.1f} GB" if total_mb >= 1024 else f"{total_mb} MB"
    print(f"would download {len(todo)} file(s), total {total_str}")

    downloads = [
        {
            "source": "url",
            "url": t["url"],
            "dest": t["dest"],
            "filename": t["filename"],
        }
        for t in todo
    ]
    print()
    print("RunPod payload:")
    print(json.dumps({"input": {"command": "download", "downloads": downloads}}, indent=2))

    if not args.execute:
        print()
        print("(dry run — pass --execute to submit this to RunPod.)")
        return 0

    api_key = os.environ.get("RUNPOD_API_KEY", "").strip()
    endpoint_id = (args.endpoint_id or os.environ.get("RUNPOD_ENDPOINT_ID", "")).strip()
    if not api_key:
        print("ERROR: RUNPOD_API_KEY env var is empty.")
        return 2
    if not endpoint_id:
        print(
            "ERROR: RunPod endpoint id is not set.\n"
            "  Pass --endpoint-id, or add RUNPOD_ENDPOINT_ID=... to .env."
        )
        return 2

    print()
    confirm = input(
        f"Submit one job with {len(todo)} download(s) ({total_str}) to RunPod endpoint "
        f"{endpoint_id}? Worker becomes billable while it pulls files (~$0.10-0.30 estimated). [y/N] "
    ).strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return 1

    print()
    try:
        result = submit_download_job(endpoint_id, api_key, downloads)
    except (HTTPError, URLError) as e:
        print(f"ERROR submitting job: {e}")
        return 3
    except TimeoutError as e:
        print(f"ERROR: {e}")
        return 4

    status = str(result.get("status", "")).upper()
    print()
    print(f"final status: {status}")

    error_field = result.get("error")
    output = result.get("output")
    if error_field:
        snippet = json.dumps(error_field, indent=2, ensure_ascii=False) if not isinstance(error_field, str) else error_field
        print(f"error:\n{snippet[:3000]}")
    if output is not None:
        print(f"output:\n{json.dumps(output, indent=2, ensure_ascii=False)[:3000]}")

    if status != "COMPLETED":
        print()
        print("Job did NOT complete cleanly. Check the output above.")
        return 5

    print()
    print("All downloads landed. Verify with:")
    print("  comfy-gen list_models  # if your CLI supports per-dest listing")
    print("Then click 'Sync' on a ComfyGen block so the LoRAs surface in the picker dropdowns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
