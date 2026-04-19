"""Mobile-specific persistent store.

All mobile (/m) features share this single file-based store:
- presets  (templates + character anchors)
- cost log (per-generation cost estimates)
- publications (tracker for Fanvue / DLsite / etc.)
- schedules (scheduled generation jobs)
- batches (batch generation groups)

Data files under {ROOT_DIR}/data/:
- m_presets.json        — list of preset dicts
- m_cost_log.jsonl      — append-only cost entries
- m_publications.json   — list of publication dicts
- m_schedules.json      — list of schedule dicts
- m_batches.json        — list of batch dicts

Functions are thread-safe via a single shared lock. Each write atomically
replaces the target file (write-to-temp + rename) to avoid corruption.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend import config

_DATA_DIR = config.ROOT_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

PRESETS_PATH = _DATA_DIR / "m_presets.json"
COST_LOG_PATH = _DATA_DIR / "m_cost_log.jsonl"
PUBLICATIONS_PATH = _DATA_DIR / "m_publications.json"
SCHEDULES_PATH = _DATA_DIR / "m_schedules.json"
BATCHES_PATH = _DATA_DIR / "m_batches.json"

_lock = threading.Lock()


# ============================================================
# Generic JSON list helpers
# ============================================================

def _load_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_list(path: Path, items: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _new_id() -> str:
    return str(uuid.uuid4())


# ============================================================
# Presets (templates + characters)
# ============================================================

def list_presets() -> list[dict[str, Any]]:
    with _lock:
        return _load_list(PRESETS_PATH)


def get_preset(preset_id: str) -> dict[str, Any] | None:
    with _lock:
        for p in _load_list(PRESETS_PATH):
            if p.get("id") == preset_id:
                return p
        return None


def save_preset(preset: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a preset. Returns the saved preset with id/timestamps filled."""
    with _lock:
        items = _load_list(PRESETS_PATH)
        now = _now_iso()
        pid = str(preset.get("id") or "").strip()
        if pid:
            # Update existing
            found = False
            for i, p in enumerate(items):
                if p.get("id") == pid:
                    preset["updated_at"] = now
                    preset.setdefault("created_at", p.get("created_at", now))
                    items[i] = preset
                    found = True
                    break
            if not found:
                preset["created_at"] = now
                preset["updated_at"] = now
                items.append(preset)
        else:
            # Insert new
            preset["id"] = _new_id()
            preset["created_at"] = now
            preset["updated_at"] = now
            items.append(preset)

        _save_list(PRESETS_PATH, items)
        return preset


def delete_preset(preset_id: str) -> bool:
    with _lock:
        items = _load_list(PRESETS_PATH)
        new_items = [p for p in items if p.get("id") != preset_id]
        if len(new_items) == len(items):
            return False
        _save_list(PRESETS_PATH, new_items)
        return True


# ============================================================
# Cost tracking
# ============================================================

# Rough cost estimates per generation (USD, RunPod A100 Serverless).
# Calibrated from user's observed ~$0.04 per 1080x1920 Z-Image at 8 steps.
COST_RATES = {
    "z_image": {
        "base": 0.012,              # fixed overhead
        "per_megapixel_step": 0.00018,  # scales with pixels * steps
    },
    "illustrious": {
        "base": 0.010,
        "per_megapixel_step": 0.00009,  # cheaper per step than Z-Image (30 steps vs 8)
    },
    "wan_i2v": {
        "base": 0.30,               # video base cost much higher
        "per_second": 0.015,        # plus per output-second cost
    },
}


def estimate_cost(
    model: str, width: int = 0, height: int = 0,
    steps: int = 0, length: int = 0, fps: int = 16,
) -> float:
    """Rough USD cost estimate for a single generation."""
    rates = COST_RATES.get(model)
    if not rates:
        return 0.04  # fallback guess
    if model == "wan_i2v":
        seconds = max(1.0, (length or 33) / max(1, fps or 16))
        return rates["base"] + seconds * rates["per_second"]
    mp = max(0.1, (width or 1024) * (height or 1024) / 1_000_000.0)
    s = max(1, steps or 8)
    return rates["base"] + mp * s * rates["per_megapixel_step"]


def log_cost(entry: dict[str, Any]) -> None:
    """Append a cost entry (one line JSON) to the log file."""
    entry.setdefault("timestamp", _now_iso())
    entry.setdefault("ts_unix", time.time())
    with _lock:
        with COST_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cost_summary(since_ts: float | None = None) -> dict[str, Any]:
    """Return totals (count + usd) with per-model breakdown and time buckets."""
    with _lock:
        if not COST_LOG_PATH.exists():
            return {"total_usd": 0.0, "total_count": 0, "by_model": {}, "today_usd": 0.0, "today_count": 0, "month_usd": 0.0, "month_count": 0}
        entries: list[dict[str, Any]] = []
        for line in COST_LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue

    now = time.time()
    today_start = now - (now % 86400)
    month_start = now - 30 * 86400

    total_usd = 0.0
    total_count = 0
    today_usd = 0.0
    today_count = 0
    month_usd = 0.0
    month_count = 0
    by_model: dict[str, dict[str, Any]] = {}

    for e in entries:
        usd = float(e.get("est_cost_usd", 0) or 0)
        ts = float(e.get("ts_unix", 0) or 0)
        model = str(e.get("model", "unknown"))

        if since_ts and ts < since_ts:
            continue

        total_usd += usd
        total_count += 1
        if ts >= today_start:
            today_usd += usd
            today_count += 1
        if ts >= month_start:
            month_usd += usd
            month_count += 1

        m = by_model.setdefault(model, {"usd": 0.0, "count": 0})
        m["usd"] += usd
        m["count"] += 1

    for m in by_model.values():
        m["usd"] = round(m["usd"], 4)

    return {
        "total_usd": round(total_usd, 4),
        "total_count": total_count,
        "today_usd": round(today_usd, 4),
        "today_count": today_count,
        "month_usd": round(month_usd, 4),
        "month_count": month_count,
        "by_model": by_model,
    }


# ============================================================
# Publications tracker
# ============================================================

def list_publications() -> list[dict[str, Any]]:
    with _lock:
        return _load_list(PUBLICATIONS_PATH)


def save_publication(pub: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        items = _load_list(PUBLICATIONS_PATH)
        now = _now_iso()
        pid = str(pub.get("id") or "").strip()
        if pid:
            for i, p in enumerate(items):
                if p.get("id") == pid:
                    pub["updated_at"] = now
                    pub.setdefault("created_at", p.get("created_at", now))
                    items[i] = pub
                    _save_list(PUBLICATIONS_PATH, items)
                    return pub
            pub["created_at"] = now
            pub["updated_at"] = now
            items.append(pub)
        else:
            pub["id"] = _new_id()
            pub["created_at"] = now
            pub["updated_at"] = now
            items.append(pub)

        _save_list(PUBLICATIONS_PATH, items)
        return pub


def delete_publication(pub_id: str) -> bool:
    with _lock:
        items = _load_list(PUBLICATIONS_PATH)
        new_items = [p for p in items if p.get("id") != pub_id]
        if len(new_items) == len(items):
            return False
        _save_list(PUBLICATIONS_PATH, new_items)
        return True


# ============================================================
# Schedules
# ============================================================

def list_schedules() -> list[dict[str, Any]]:
    with _lock:
        return _load_list(SCHEDULES_PATH)


def save_schedule(sched: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        items = _load_list(SCHEDULES_PATH)
        now = _now_iso()
        sid = str(sched.get("id") or "").strip()
        if sid:
            for i, s in enumerate(items):
                if s.get("id") == sid:
                    sched["updated_at"] = now
                    sched.setdefault("created_at", s.get("created_at", now))
                    items[i] = sched
                    _save_list(SCHEDULES_PATH, items)
                    return sched
        sched["id"] = _new_id()
        sched["created_at"] = now
        sched["updated_at"] = now
        items.append(sched)
        _save_list(SCHEDULES_PATH, items)
        return sched


def delete_schedule(sched_id: str) -> bool:
    with _lock:
        items = _load_list(SCHEDULES_PATH)
        new_items = [s for s in items if s.get("id") != sched_id]
        if len(new_items) == len(items):
            return False
        _save_list(SCHEDULES_PATH, new_items)
        return True


# ============================================================
# Batches
# ============================================================

def list_batches() -> list[dict[str, Any]]:
    with _lock:
        return _load_list(BATCHES_PATH)


def get_batch(batch_id: str) -> dict[str, Any] | None:
    with _lock:
        for b in _load_list(BATCHES_PATH):
            if b.get("id") == batch_id:
                return b
        return None


def save_batch(batch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        items = _load_list(BATCHES_PATH)
        now = _now_iso()
        bid = str(batch.get("id") or "").strip()
        if bid:
            for i, b in enumerate(items):
                if b.get("id") == bid:
                    batch["updated_at"] = now
                    batch.setdefault("created_at", b.get("created_at", now))
                    items[i] = batch
                    _save_list(BATCHES_PATH, items)
                    return batch
        batch["id"] = _new_id()
        batch["created_at"] = now
        batch["updated_at"] = now
        items.append(batch)
        _save_list(BATCHES_PATH, items)
        return batch


def delete_batch(batch_id: str) -> bool:
    with _lock:
        items = _load_list(BATCHES_PATH)
        new_items = [b for b in items if b.get("id") != batch_id]
        if len(new_items) == len(items):
            return False
        _save_list(BATCHES_PATH, new_items)
        return True
