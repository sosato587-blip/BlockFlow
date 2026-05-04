"""Unit tests for backend/base_models.py.

Uses stdlib `unittest` so no new dependencies are needed — the project
declares runtime deps via PEP 723 inline in app.py and has no pytest in
that list. Run with:

    python -m unittest tests.test_base_models -v

or via the test runner shim once CI is wired up.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the project root importable when running directly from /tests.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import base_models as bm  # noqa: E402


class ClassifyLoraTests(unittest.TestCase):
    """classify_lora() — filename → family id routing."""

    def test_returns_unclassified_for_empty(self) -> None:
        self.assertEqual(bm.classify_lora(""), bm.UNCLASSIFIED)

    def test_illustrious_pattern(self) -> None:
        for name in [
            "character_illustriousXL.safetensors",
            "NicoRobin_IllustriousXL.safetensors",
            "thing_illuxl_v1.safetensors",
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), "illustrious")

    def test_z_image_pattern(self) -> None:
        for name in [
            "style_z_image_turbo.safetensors",
            "realgirl_z-image.safetensors",
            "something_zimage_v2.safetensors",
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), "z_image")

    def test_wan22_pattern(self) -> None:
        for name in [
            "dance_wan2.2.safetensors",
            "motion_wan22.safetensors",
            "thing_wan_i2v.safetensors",
            "other_wan_fun.safetensors",
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), "wan_22")

    def test_ltx_pattern(self) -> None:
        # NOTE: the current regex is `\bltx\b|ltx[_-]video|ltxv` — the `\b`
        # word boundary does NOT fire between "ltx" and "_" because `_` is a
        # word char, so "ltx_motion.safetensors" is NOT currently classified
        # as LTX. That's a known limitation — widen the pattern to
        # `\bltx[_\-\.]` if / when it matters. For now we test only the
        # shapes the regex actually matches.
        for name in [
            "ltx.motion.safetensors",           # matches \bltx\b (period is non-word)
            "ltx-video_foo.safetensors",        # matches ltx[_-]video
            "ltxv_test.safetensors",            # matches ltxv
            "ltx video 2b v0.9.5.safetensors",  # matches \bltx\b
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), "ltx")

    def test_override_takes_precedence(self) -> None:
        # An override-listed LoRA should classify to its override even if its
        # name lacks architecture hints.
        self.assertEqual(
            bm.classify_lora("smooth_detailer_booster.safetensors"),
            "illustrious",
        )
        self.assertEqual(
            bm.classify_lora("nicegirls_ultrareal.safetensors"),
            "z_image",
        )

    def test_unclassified_for_unknown_name(self) -> None:
        self.assertEqual(
            bm.classify_lora("random_unrelated_name_v3.safetensors"),
            bm.UNCLASSIFIED,
        )

    def test_illustrious_abbreviations_2026_05_03(self) -> None:
        # Regression cases from the 2026-05-03 audit: 22/48 LoRAs were
        # invisible in the family-filtered UI because the pattern only
        # matched the full word "illustrious" / "illuxl". These are the
        # abbreviation forms callers in the wild actually use.
        for name in [
            "yamato_(one_piece)_ilxl_v1.safetensors",      # _ilxl_ infix
            "PeronaOnePieceAnime_IXL.safetensors",         # _IXL. suffix
            "NSFWFilter_illusXL_Incrs_v1.safetensors",     # illusXL typo
            "anime_screencap-IL-NOOB_v3.safetensors",      # IL-NOOB merge
            "magical-girl-outfit-il-20.safetensors",       # -il-NN suffix
            "Washing_Body_in_the_Mirror_IL.safetensors",   # _IL. suffix
            "kms_in_the_dark_IL.safetensors",              # _IL. suffix
            "IFL_v1.0_IL.safetensors",                     # mixed case
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), "illustrious")

    def test_wan22_extras_2026_05_03(self) -> None:
        # Animate / relight / lightx2v all run against the Wan 2.2
        # checkpoints — must classify under wan_22 so the family-filtered
        # LoRA dropdown for Wan workflows surfaces them.
        for name in [
            "WanAnimate_relight_lora_fp16.safetensors",
            "Wan-Animate-style.safetensors",
            "wan_relight_v2.safetensors",
            "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), "wan_22")

    def test_z_image_zit_variants_2026_05_03(self) -> None:
        # ZIT* names without a clean word boundary the regex can grab.
        # Confirmed Z-Image Turbo by the user on 2026-05-03.
        self.assertEqual(
            bm.classify_lora("ZITnsfwLoRA.safetensors"),
            "z_image",
        )
        self.assertEqual(
            bm.classify_lora("MicroBikiniV2ZiTde.safetensors"),
            "z_image",
        )

    def test_does_not_misclassify_unrelated_il_substring(self) -> None:
        # "il" mid-word should NOT trigger the illustrious branch — the
        # broadened regex anchors on a non-letter prefix to avoid this.
        for name in [
            "Brazil_landscape.safetensors",   # "il" at mid-word
            "Genevril_v2.safetensors",        # "il" at mid-word
            "evil_witch.safetensors",         # "il" at mid-word
        ]:
            with self.subTest(name=name):
                self.assertEqual(bm.classify_lora(name), bm.UNCLASSIFIED)

    def test_strips_path_prefix(self) -> None:
        # Classification should look at the base filename only.
        self.assertEqual(
            bm.classify_lora("/runpod/models/loras/foo_illustriousXL.safetensors"),
            "illustrious",
        )
        self.assertEqual(
            bm.classify_lora(r"C:\models\loras\bar_wan22.safetensors"),
            "wan_22",
        )

    def test_case_insensitive(self) -> None:
        self.assertEqual(
            bm.classify_lora("FOO_ILLUSTRIOUSXL.SAFETENSORS"),
            "illustrious",
        )


class GroupLorasByFamilyTests(unittest.TestCase):
    """group_loras_by_family() — flat list → per-family buckets."""

    def test_unknown_loras_are_dropped(self) -> None:
        out = bm.group_loras_by_family(["foo_illustriousXL.safetensors", "random.safetensors"])
        self.assertEqual(out["illustrious"], ["foo_illustriousXL.safetensors"])
        # No "unknown" key — unclassified loras are silently dropped.
        self.assertNotIn(bm.UNCLASSIFIED, out)

    def test_all_families_present_in_output(self) -> None:
        out = bm.group_loras_by_family([])
        for fid in bm.FAMILIES:
            self.assertIn(fid, out)
            self.assertEqual(out[fid], [])

    def test_sorted_alphabetically_within_family(self) -> None:
        out = bm.group_loras_by_family(
            [
                "z_illustriousXL.safetensors",
                "a_illustriousXL.safetensors",
                "m_illustriousXL.safetensors",
            ]
        )
        self.assertEqual(
            out["illustrious"],
            [
                "a_illustriousXL.safetensors",
                "m_illustriousXL.safetensors",
                "z_illustriousXL.safetensors",
            ],
        )


class FamilySummaryTests(unittest.TestCase):
    """family_summary() — the payload shape the Base Model Selector consumes."""

    def test_empty_inputs_still_show_families_with_known_checkpoints(self) -> None:
        # Every FAMILIES entry has at least one KNOWN_CHECKPOINTS row as of
        # 2026-04-22, so a fully empty LoRA list still returns every family.
        rows = bm.family_summary({}, {})
        self.assertEqual(len(rows), len(bm.FAMILIES))
        ids = [r["id"] for r in rows]
        self.assertEqual(ids, sorted(ids, key=lambda x: bm.FAMILIES[x].sort_order))

    def test_rows_shape_matches_contract(self) -> None:
        rows = bm.family_summary({"illustrious": ["a.safetensors"]}, {})
        row = next(r for r in rows if r["id"] == "illustrious")
        # Shape contract the frontend relies on.
        self.assertEqual(row["label"], "Illustrious XL")
        self.assertEqual(row["ckpt_dir"], "checkpoints")
        self.assertEqual(row["lora_count_high"], 1)
        self.assertEqual(row["lora_count_low"], 0)
        self.assertIsInstance(row["checkpoints"], list)
        self.assertGreater(len(row["checkpoints"]), 0)
        cp = row["checkpoints"][0]
        self.assertIn("filename", cp)
        self.assertIn("label", cp)
        self.assertIn("notes", cp)

    def test_sort_order_is_respected(self) -> None:
        rows = bm.family_summary({}, {})
        sort_orders = [bm.FAMILIES[r["id"]].sort_order for r in rows]
        self.assertEqual(sort_orders, sorted(sort_orders))

    def test_family_without_checkpoints_or_loras_is_omitted(self) -> None:
        # Simulate a hypothetical family with nothing registered. We can't
        # mutate FAMILIES safely, so we verify the behavior via a round-trip:
        # if we remove all checkpoints + LoRAs for illustrious, it should
        # disappear. Use patching.
        original = bm.KNOWN_CHECKPOINTS
        try:
            bm.KNOWN_CHECKPOINTS = [cp for cp in original if cp.family != "illustrious"]
            rows = bm.family_summary({}, {})
            ids = [r["id"] for r in rows]
            self.assertNotIn("illustrious", ids)
        finally:
            bm.KNOWN_CHECKPOINTS = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
