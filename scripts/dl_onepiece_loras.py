"""DL helper for the One Piece female-character LoRA set.

Reads the BlockFlow LoRA cache (``comfy_gen_info_cache.json``, populated
by the ComfyGen block's Sync button) to learn what's already on the
RunPod network volume, queries Civitai's public API for the 6 target
models to get their canonical filenames, and prints the
``comfy-gen download --source url ...`` commands for the ones that
aren't there yet. Pass ``--execute`` to actually run them (prompts for
confirmation; each ``comfy-gen`` invocation hits the RunPod handler so
this **costs money**).

Note on the download mode:
  We intentionally use ``--source url`` (with civitai's REST download
  endpoint) instead of ``--source civitai``. As of 2026-04 the worker
  image's civitai-specific code path is broken — it calls a missing
  ``/tools/civitai-downloader/download_with_aria.py`` and exits 2.
  The url path goes through the worker's generic downloader, which
  works for both HuggingFace and civitai.

  If a CIVITAI_API_KEY env var is set when this script runs, the
  token is embedded in the URL as ``?token=...`` so login-gated
  models still download. Without the env var, only public models will
  succeed (civitai returns 401 otherwise, and the script stops).

Usage on the mini PC:

    # Read-only — preview what would change.
    uv run scripts/dl_onepiece_loras.py

    # Same, but execute the missing downloads after a y/N prompt.
    uv run scripts/dl_onepiece_loras.py --execute

If the cache file is empty / stale, click "Sync" on a ComfyGen block
once or wait for the auto-refresh.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
    """Replace ``token=<key>`` with ``token=***...***`` for safe printing."""
    if "token=" not in arg:
        return arg
    head, sep, tail = arg.partition("token=")
    end = tail.find("&")
    val = tail if end == -1 else tail[:end]
    rest = "" if end == -1 else tail[end:]
    masked = f"{val[:4]}...{val[-4:]}" if len(val) >= 8 else "***"
    return f"{head}{sep}{masked}{rest}"


def render_commands(plan: list[dict], token: str | None) -> list[list[str]]:
    """Return [[argv0, argv1, ...], ...] for each missing entry.

    Uses ``--source url`` because the worker's ``--source civitai`` path
    is currently broken (missing /tools/civitai-downloader/download_with_aria.py).
    """
    cmds = []
    for p in plan:
        if not p.get("exists") and "version_id" in p:
            url = _build_civitai_url(int(p["version_id"]), token)
            cmds.append([
                "comfy-gen", "download",
                "--source", "url",
                "--url", url,
                "--dest", "loras",
                "--filename", str(p["filename"]),
            ])
    return cmds


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
        # Print a redacted hint so the user can verify the right key is being used.
        masked = f"{civitai_token[:4]}...{civitai_token[-4:]}" if len(civitai_token) >= 8 else "(short)"
        print(f"using CIVITAI_API_KEY from env ({masked}) for url-mode downloads")
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

    cmds = render_commands(plan, civitai_token)
    print("commands:")
    for c in cmds:
        # Mask the token in the printed URL.
        printable = [a if "token=" not in a else _mask_token_in_url(a) for a in c]
        print(f"  {' '.join(printable)}")

    if not args.execute:
        print()
        print("(dry run — pass --execute to actually run these.)")
        return 0

    print()
    confirm = input(f"Execute {len(cmds)} downloads? This hits RunPod (cost: free for download but billable for active worker). [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return 1

    for cmd in cmds:
        printable = [_mask_token_in_url(a) for a in cmd]
        print(f"\n>>> {' '.join(printable)}")
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            print("  ERROR: 'comfy-gen' CLI not found on PATH.")
            return 2
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: command exited {e.returncode}; stopping.")
            return e.returncode

    print()
    print("All downloads complete. Verify on the RunPod side with:")
    print("  comfy-gen list loras")
    print("Then click 'Sync' on a ComfyGen block to refresh BlockFlow's cache.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
