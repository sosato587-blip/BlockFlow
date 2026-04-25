"""Parity tests with frontend/src/lib/lora-mapping.test.ts.

Each case mirrors the 5-case heuristic documented in
``backend/lora_mapping.py`` and ``frontend/src/lib/lora-mapping.ts``.
"""

from __future__ import annotations

from backend.lora_mapping import (
    LoraLoaderNode,
    LoraPick,
    compute_inline_lora_overrides,
)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_case_5_no_loader_nodes_returns_empty() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[],
        inline_high=[LoraPick("a.safetensors", 1.0)],
        inline_low=[],
    )
    assert out == {}


def test_empty_picks_returns_empty() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[LoraLoaderNode("n1")],
        inline_high=[],
        inline_low=[],
    )
    assert out == {}


# ---------------------------------------------------------------------------
# Case 1: single loader
# ---------------------------------------------------------------------------


def test_case_1_single_loader_merges_both_branches() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[LoraLoaderNode("n1")],
        inline_high=[LoraPick("a.safetensors", 0.8)],
        inline_low=[LoraPick("b.safetensors", 0.5)],
    )
    # Merged list is [a, b]; only first pick ("a") fits the single slot.
    assert out == {
        "n1.lora_name": "a.safetensors",
        "n1.strength_model": "0.8",
        "n1.strength_clip": "0.8",
    }


# ---------------------------------------------------------------------------
# Case 2: label hints
# ---------------------------------------------------------------------------


def test_case_2_labels_split_by_hints() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[
            LoraLoaderNode("n1", label="high noise stage"),
            LoraLoaderNode("n2", label="low noise stage"),
        ],
        inline_high=[LoraPick("h.safetensors", 1.0)],
        inline_low=[LoraPick("l.safetensors", 0.6)],
    )
    assert out["n1.lora_name"] == "h.safetensors"
    assert out["n2.lora_name"] == "l.safetensors"
    assert out["n1.strength_model"] == "1.0"
    assert out["n2.strength_model"] == "0.6"


def test_case_2_only_high_labeled_falls_through_unlabeled_for_low() -> None:
    # If only one branch is labeled, the other picks still land on any
    # leftover nodes (unlabeled ones).
    out = compute_inline_lora_overrides(
        lora_nodes=[
            LoraLoaderNode("n1", label="high"),
            LoraLoaderNode("n2"),
        ],
        inline_high=[LoraPick("h.safetensors", 1.0)],
        inline_low=[],
    )
    assert out["n1.lora_name"] == "h.safetensors"
    assert "n2.lora_name" not in out


# ---------------------------------------------------------------------------
# Case 3: two nodes, no hints
# ---------------------------------------------------------------------------


def test_case_3_two_nodes_no_hints_assumes_order() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[LoraLoaderNode("n1"), LoraLoaderNode("n2")],
        inline_high=[LoraPick("h.safetensors", 1.0)],
        inline_low=[LoraPick("l.safetensors", 0.6)],
    )
    assert out["n1.lora_name"] == "h.safetensors"
    assert out["n2.lora_name"] == "l.safetensors"


# ---------------------------------------------------------------------------
# Case 4: many nodes, no hints
# ---------------------------------------------------------------------------


def test_case_4_many_nodes_no_hints_sequential() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[
            LoraLoaderNode("n1"),
            LoraLoaderNode("n2"),
            LoraLoaderNode("n3"),
        ],
        inline_high=[
            LoraPick("h1.safetensors", 1.0),
            LoraPick("h2.safetensors", 0.9),
        ],
        inline_low=[LoraPick("l1.safetensors", 0.6)],
    )
    # Sequential: h1 -> n1, h2 -> n2, l1 -> n3
    assert out["n1.lora_name"] == "h1.safetensors"
    assert out["n2.lora_name"] == "h2.safetensors"
    assert out["n3.lora_name"] == "l1.safetensors"


# ---------------------------------------------------------------------------
# Overflow / preservation semantics
# ---------------------------------------------------------------------------


def test_picks_beyond_slots_are_dropped_silently() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[LoraLoaderNode("n1")],
        inline_high=[
            LoraPick("a.safetensors", 1.0),
            LoraPick("b.safetensors", 0.5),
        ],
        inline_low=[],
    )
    assert out["n1.lora_name"] == "a.safetensors"
    # Only "a" lands; "b" is silently dropped.
    assert "b.safetensors" not in out.values()


def test_existing_overrides_are_not_clobbered() -> None:
    out = compute_inline_lora_overrides(
        lora_nodes=[LoraLoaderNode("n1")],
        inline_high=[LoraPick("a.safetensors", 1.0)],
        inline_low=[],
        existing_overrides={"n1.lora_name": "preset.safetensors"},
    )
    assert "n1.lora_name" not in out
    assert out["n1.strength_model"] == "1.0"
    assert out["n1.strength_clip"] == "1.0"


def test_does_not_mutate_existing_overrides_dict() -> None:
    existing: dict[str, str] = {"n1.lora_name": "preset.safetensors"}
    compute_inline_lora_overrides(
        lora_nodes=[LoraLoaderNode("n1")],
        inline_high=[LoraPick("a.safetensors", 1.0)],
        inline_low=[],
        existing_overrides=existing,
    )
    assert existing == {"n1.lora_name": "preset.safetensors"}
