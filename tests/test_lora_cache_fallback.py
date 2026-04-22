"""Unit tests for backend.services._read_comfy_gen_lora_cache.

The function is a fallback LoRA source used when `LORA_SOURCE_SSH_TARGET`
isn't configured (the default on the mini PC). It reads a JSON cache
written by `comfy-gen info`. Must be robust to:
  1. Missing file (happens on a fresh install before the first Sync)
  2. Broken JSON (can happen if comfy-gen crashed mid-write)
  3. Empty / non-list `loras` field
  4. Non-string entries mixed in (defensive)

Run with:
    python -m unittest tests.test_lora_cache_fallback -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import services  # noqa: E402


class ReadComfyGenLoraCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.cache_path = Path(self.tmpdir.name) / "comfy_gen_info_cache.json"
        # Patch config.COMFY_GEN_INFO_CACHE_PATH to our temp file.
        self._patcher = mock.patch.object(
            services.config, "COMFY_GEN_INFO_CACHE_PATH", self.cache_path
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_returns_empty_when_file_missing(self) -> None:
        self.assertFalse(self.cache_path.exists())
        self.assertEqual(services._read_comfy_gen_lora_cache(), [])

    def test_returns_empty_on_broken_json(self) -> None:
        self.cache_path.write_text("{not valid json", encoding="utf-8")
        # Must NOT raise — the fallback is best-effort.
        self.assertEqual(services._read_comfy_gen_lora_cache(), [])

    def test_returns_empty_when_loras_missing(self) -> None:
        self.cache_path.write_text(json.dumps({"other": []}), encoding="utf-8")
        self.assertEqual(services._read_comfy_gen_lora_cache(), [])

    def test_returns_empty_when_loras_null(self) -> None:
        self.cache_path.write_text(json.dumps({"loras": None}), encoding="utf-8")
        self.assertEqual(services._read_comfy_gen_lora_cache(), [])

    def test_returns_flat_list_of_strings(self) -> None:
        payload = {"loras": ["a.safetensors", "b.safetensors", "c.safetensors"]}
        self.cache_path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(
            services._read_comfy_gen_lora_cache(),
            ["a.safetensors", "b.safetensors", "c.safetensors"],
        )

    def test_filters_non_string_entries(self) -> None:
        # Defensive: if the cache ever grows an object entry (e.g. from a
        # future comfy-gen version with richer metadata), we strip to strings
        # only so the caller's string-typed list stays clean.
        payload = {
            "loras": [
                "good.safetensors",
                {"name": "object_form.safetensors"},
                123,
                None,
                "also_good.safetensors",
            ],
        }
        self.cache_path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(
            services._read_comfy_gen_lora_cache(),
            ["good.safetensors", "also_good.safetensors"],
        )

    def test_returns_empty_on_unreadable_file(self) -> None:
        # Simulate an IO error by pointing the cache at a directory — open()
        # will raise, and the bare `except Exception` must swallow it.
        self.cache_path.mkdir()
        self.assertEqual(services._read_comfy_gen_lora_cache(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
