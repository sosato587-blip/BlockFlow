"""DL helper for the One Piece female-character LoRA set.

Reads the BlockFlow LoRA cache (``comfy_gen_info_cache.json``, populated
by the ComfyGen block's Sync button) to learn what's already on the
RunPod network volume, queries Civitai's public API for the 6 target
models to get their canonical filenames, and submits **one combined
download job** to RunPod for the ones that aren't there yet. Pass
``--execute`` to actually submit it (prompts for confirmation;
hitting the RunPod handler **costs money** while the worker is alive).

Why we POST RunPod directly instead of shelling out to comfy-gen:
  * The worker's ``--source civitai`` path is currently broken (calls
    a missing ``/tools/civitai-downloader/download_with_aria.py``).
  * The installed ``comfy-gen`` CLI doesn't expose a ``--source url``
    flag, so we can't reuse the LTX_QUICKSTART pattern verbatim.
  * The worker handler itself accepts the same JSON shape that
    ``backend/m_routes.py`` already uses for the IP-Adapter / ADetailer /
    ControlNet auto-DL endpoints (``input.command="download"``,
    ``input.downloads=[{source:"url", url, dest, filename}]``), so we
    just construct that JSON locally and POST it.

Required env vars (already set on the mini PC's .env for normal
BlockFlow operation):
  * RUNPOD_API_KEY     — Bearer token for RunPod Serverless
  * RUNPOD_ENDPOINT_ID — your worker's endpoint id
  * CIVITAI_API_KEY    — optional, but required for login-gated models

Usage on the mini PC:

    # Read-only — preview what would change.
    uv run scripts/dl_onepiece_loras.py

    # Same, but submit + poll the combined download job.
    uv run scripts/dl_onepiece_loras.py --execute

If the cache file is empty / stale, click "Sync" on a ComfyGen block
once or wait for the auto-refresh.
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
CACHE_PATH = REPO_ROOT / "comfy_gen_info_cache.json"

# Civitai model IDs to check / download. Order is the order downloads will
# be attempted. ``label`` is human-friendly; ``model_id`` drives the API.
TARGETS: list[dict[str, str | int]] = [
    {"model_id": 1395156, "label": "Nami (4 outfits)"},
    {"model_id": 1481673, "label": "Nico Robin"},
    {"model_id": 1826710, "label": "Boa Hancock"},
    {"model_id": 1249564, "label": "Yamato"},
    {"model_id": 887196,  "label": "Perona (Ghost Princess)"},
    {"model_id": 1646155, "label": "One Piece Manga Style"},
]

CIVITAI_API = "https://civitai.com/api/v1/models/{model_id}"


def load_existing_loras() -> tuple[list[str], str]:
    """Return (filenames, source_description). Empty list if cache is missing."""
    if not CACHE_PATH.exists():
        return [], f"(no cache file at {CACHE_PATH} — run ComfyGen Sync first)"
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [], f"(failed to parse {CACHE_PATH}: {e})"
    loras = [str(x) for x in (data.get("loras") or []) if isinstance(x, str)]
    fetched_at = data.get("fetched_at")
    age = ""
    if fetched_at:
        import time
        age = f", age={int(time.time() - float(fetched_at))}s"
    return loras, f"{CACHE_PATH.name} ({len(loras)} entries{age})"


def fetch_civitai(model_id: int) -> dict | None:
    """Fetch one model's metadata from civitai. Returns None on hard failure."""
    req = Request(
        CIVITAI_API.format(model_id=model_id),
        headers={"User-Agent": "BlockFlow-onepiece-dl/1.0"},
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"  HTTP {e.code} for model {model_id}: {e.reason}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"  URL error for model {model_id}: {e.reason}", file=sys.stderr)
        return None
    except (TimeoutError, json.JSONDecodeError) as e:
        print(f"  fetch failed for model {model_id}: {e}", file=sys.stderr)
        return None


def pick_primary_file(version: dict) -> dict | None:
    """Pick the .safetensors file from a modelVersion's files list."""
    files = version.get("files") or []
    # Prefer ``primary`` flag, then type=Model, else first .safetensors.
    for f in files:
        if isinstance(f, dict) and f.get("primary"):
            return f
    for f in files:
        if isinstance(f, dict) and f.get("type") == "Model":
            return f
    for f in files:
        if isinstance(f, dict) and str(f.get("name", "")).lower().endswith(".safetensors"):
            return f
    return None


def resolve_targets() -> list[dict]:
    """Hit Civitai for each target -> add version_id, filename, size, exists."""
    out: list[dict] = []
    for t in TARGETS:
        model_id = int(t["model_id"])
        print(f"resolving #{model_id} ({t['label']})...", flush=True)
        meta = fetch_civitai(model_id)
        if meta is None:
            out.append({**t, "error": "civitai fetch failed"})
            continue
        versions = meta.get("modelVersions") or []
        if not versions:
            out.append({**t, "error": "no modelVersions"})
            continue
        v = versions[0]
        f = pick_primary_file(v)
        if f is None:
            out.append({**t, "error": "no model file in latest version"})
            continue
        size_mb = round(float(f.get("sizeKB") or 0) / 1024, 1)
        triggers = ", ".join(v.get("trainedWords") or [])
        out.append({
            **t,
            "model_name": meta.get("name", ""),
            "nsfw": bool(meta.get("nsfw", False)),
            "version_id": int(v.get("id")),
            "version_name": v.get("name", ""),
            "base_model": v.get("baseModel", ""),
            "filename": f.get("name", ""),
            "size_mb": size_mb,
            "triggers": triggers,
        })
    return out


def diff_against_existing(plan: list[dict], existing: list[str]) -> None:
    """Mutates each plan entry with ``exists=True/False`` and a diagnostic."""
    existing_lower = {x.lower() for x in existing}
    # Substring buckets per character (rough first-pass match) for cases where
    # the user previously downloaded a different version of the same character.
    keywords_per_target: dict[int, tuple[str, ...]] = {
        1395156: ("nami",),
        1481673: ("robin", "nico"),
        1826710: ("hancock", "boa"),
        1249564: ("yamato",),
        887196:  ("perona",),
        1646155: ("onepiece", "one_piece", "one-piece", "opmanga", "opm-style", "opm_style"),
    }
    for p in plan:
        if "filename" not in p:
            p["exists"] = False
            p["match_note"] = "(metadata fetch failed)"
            continue
        fn_lower = str(p["filename"]).lower()
        exact = fn_lower in existing_lower
        kws = keywords_per_target.get(int(p["model_id"]), ())
        related = [x for x in existing if any(k in x.lower() for k in kws)]
        p["exists"] = exact
        if exact:
            p["match_note"] = "exact filename already present"
        elif related:
            p["match_note"] = f"similar ({len(related)}): {', '.join(related[:3])}{'...' if len(related) > 3 else ''}"
        else:
            p["match_note"] = "(no related entry on volume)"


def render_table(plan: list[dict]) -> None:
    headers = ("ModelID", "Exists?", "Size", "Filename", "Match note")
    rows = []
    for p in plan:
        if "filename" in p:
            mark = "[skip]" if p.get("exists") else "[NEW]"
            rows.append((str(p["model_id"]), mark, f"{p['size_mb']}MB",
                         str(p["filename"]), p["match_note"]))
        else:
            rows.append((str(p["model_id"]), "[ERR]", "-", "-",
                         p.get("error", "(unknown)")))
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print()
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*r))
    print()


def _build_civitai_url(version_id: int, token: str | None) -> str:
    """Construct the civitai REST download URL, with optional API token query."""
    base = f"https://civitai.com/api/download/models/{version_id}"
    return f"{base}?token={token}" if token else base


def _mask_token_in_url(arg: str) -> str:
    """Replace ``token=<key>`` with ``token=abcd...wxyz`` for safe printing."""
    if "token=" not in arg:
        return arg
    head, sep, tail = arg.partition("token=")
    end = tail.find("&")
    val = tail if end == -1 else tail[:end]
    rest = "" if end == -1 else tail[end:]
    masked = f"{val[:4]}...{val[-4:]}" if len(val) >= 8 else "***"
    return f"{head}{sep}{masked}{rest}"


def render_downloads(plan: list[dict], token: str | None) -> list[dict]:
    """Build the ``downloads`` array passed to the RunPod handler.

    Each entry follows the same shape m_routes.py uses for IP-Adapter /
    ADetailer / ControlNet auto-DL: ``{source, url, dest, filename}``.
    """
    out: list[dict] = []
    for p in plan:
        if not p.get("exists") and "version_id" in p:
            out.append({
                "source": "url",
                "url": _build_civitai_url(int(p["version_id"]), token),
                "dest": "loras",
                "filename": str(p["filename"]),
            })
    return out


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
    poll_timeout_sec: float = 1200.0,  # 20 min — large LoRAs over slow links
    poll_interval_sec: float = 5.0,
) -> dict:
    """POST one combined download job, then poll until terminal."""
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--execute", action="store_true",
        help="Actually run the comfy-gen download commands "
             "(after a y/N prompt). Without this, only prints the plan.",
    )
    args = ap.parse_args()

    existing, source = load_existing_loras()
    print(f"existing LoRA inventory: {source}")
    if not existing:
        print("  -> nothing to compare against; every target will be marked NEW.")
    print()

    plan = resolve_targets()
    diff_against_existing(plan, existing)
    render_table(plan)

    new_plan = [p for p in plan if not p.get("exists") and "version_id" in p]
    if not new_plan:
        print("All targets already present (or fetch failed). Nothing to download.")
        return 0

    civitai_token = os.environ.get("CIVITAI_API_KEY", "").strip() or None
    if civitai_token:
        masked = f"{civitai_token[:4]}...{civitai_token[-4:]}" if len(civitai_token) >= 8 else "(short)"
        print(f"using CIVITAI_API_KEY from env ({masked}) for civitai download URLs")
    else:
        print("CIVITAI_API_KEY not set — civitai download URLs will be unauthenticated. "
              "Login-gated models will fail with HTTP 401.")
    print()

    total_mb = round(sum(p["size_mb"] for p in new_plan), 1)
    print(f"would download {len(new_plan)} new LoRA(s), total {total_mb} MB:")
    for p in new_plan:
        triggers = f"  triggers: {p['triggers']}" if p.get("triggers") else ""
        print(f"  - {p['filename']} ({p['size_mb']} MB){triggers}")
    print()

    downloads = render_downloads(plan, civitai_token)
    print("RunPod download payload (one combined job):")
    print(json.dumps(
        {"input": {"command": "download", "downloads": [
            {**d, "url": _mask_token_in_url(d["url"])} for d in downloads
        ]}},
        indent=2,
    ))

    if not args.execute:
        print()
        print("(dry run — pass --execute to submit this to RunPod.)")
        return 0

    api_key = os.environ.get("RUNPOD_API_KEY", "").strip()
    endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()
    if not api_key:
        print("ERROR: RUNPOD_API_KEY env var is empty. Set it (it's already in .env "
              "for normal BlockFlow operation) and retry.")
        return 2
    if not endpoint_id:
        print("ERROR: RUNPOD_ENDPOINT_ID env var is empty. Set it and retry.")
        return 2

    print()
    confirm = input(
        f"Submit one job with {len(downloads)} download(s) to RunPod endpoint "
        f"{endpoint_id}? Worker becomes billable while it pulls files. [y/N] "
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
    output = result.get("output")
    print()
    print(f"final status: {status}")
    if output is not None:
        print(f"output: {json.dumps(output, indent=2, ensure_ascii=False)[:1500]}")

    if status != "COMPLETED":
        print()
        print("Job did NOT complete cleanly. Check the output above for handler errors. "
              "Common causes: RUNPOD balance, worker image bug, civitai 401 on a "
              "login-gated model.")
        return 5

    print()
    print("All downloads requested. Verify on RunPod with `comfy-gen list loras`, "
          "then click 'Sync' on a ComfyGen block to refresh BlockFlow's cache.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
