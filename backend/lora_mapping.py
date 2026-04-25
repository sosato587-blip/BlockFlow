"""Pure helper that maps inline High / Low LoRA picks onto detected LoRA
loader nodes in a parsed ComfyUI workflow.

Python port of ``frontend/src/lib/lora-mapping.ts`` (the canonical TS
version). Both implementations MUST stay in lock-step; any change to the
heuristic here must be mirrored in the TS file and vice versa. Once
S2-full converges client and server, one of the two will be retired.

Heuristic (priority order):
    1. ``len(lora_nodes) == 1``      -> merge both branches, feed all picks.
    2. ``len(lora_nodes) >= 2`` with ``"high"``/``"low"`` label hints
                                     -> split by label, preserve order within branch.
    3. ``len(lora_nodes) == 2`` without label hints
                                     -> assume ``[high, low]`` by node order.
    4. ``len(lora_nodes) > 2`` without label hints
                                     -> feed ``[*high, *low]`` sequentially.
    5. ``len(lora_nodes) == 0``      -> no-op; caller surfaces a UI warning.

Semantics callers can depend on:
    * The function NEVER overwrites an override already set in
      ``existing_overrides``. This preserves upstream wiring or user-typed values.
    * ``strength_model`` and ``strength_clip`` are set to the same value per pick.
    * Picks beyond the available loader slots are silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LoraPick:
    name: str
    strength: float


@dataclass(frozen=True)
class LoraLoaderNode:
    node_id: str
    label: Optional[str] = None


OverrideMap = dict[str, str]


_HIGH_RE = re.compile(r"high", re.IGNORECASE)
_LOW_RE = re.compile(r"low", re.IGNORECASE)


def compute_inline_lora_overrides(
    *,
    lora_nodes: list[LoraLoaderNode],
    inline_high: list[LoraPick],
    inline_low: list[LoraPick],
    existing_overrides: Optional[OverrideMap] = None,
) -> OverrideMap:
    """Return ONLY the new override keys; does not mutate inputs.

    Mirrors ``computeInlineLoraOverrides`` in
    ``frontend/src/lib/lora-mapping.ts``. See that file for further
    documentation of the heuristic and semantics.
    """
    existing = existing_overrides or {}
    out: OverrideMap = {}

    # Case 5: no loader nodes.
    if not lora_nodes:
        return out
    if not inline_high and not inline_low:
        return out

    def apply_picks(
        picks: list[LoraPick], nodes: list[LoraLoaderNode]
    ) -> None:
        for idx, pick in enumerate(picks):
            if idx >= len(nodes):
                return  # more picks than slots -> drop the excess
            node = nodes[idx]
            name_key = f"{node.node_id}.lora_name"
            sm_key = f"{node.node_id}.strength_model"
            sc_key = f"{node.node_id}.strength_clip"
            if existing.get(name_key) is None and out.get(name_key) is None:
                out[name_key] = pick.name
            if existing.get(sm_key) is None and out.get(sm_key) is None:
                out[sm_key] = str(pick.strength)
            if existing.get(sc_key) is None and out.get(sc_key) is None:
                out[sc_key] = str(pick.strength)

    # Case 1: single loader - no high/low distinction possible.
    if len(lora_nodes) == 1:
        apply_picks([*inline_high, *inline_low], lora_nodes)
        return out

    high_nodes = [
        n for n in lora_nodes if n.label and _HIGH_RE.search(n.label)
    ]
    low_nodes = [
        n for n in lora_nodes if n.label and _LOW_RE.search(n.label)
    ]

    # Case 2: labels usable.
    if high_nodes or low_nodes:
        apply_picks(inline_high, high_nodes if high_nodes else lora_nodes)
        apply_picks(inline_low, low_nodes)
        return out

    # Case 3: two nodes, no label hints -> assume [high, low] by order.
    if len(lora_nodes) == 2:
        apply_picks(inline_high, [lora_nodes[0]])
        apply_picks(inline_low, [lora_nodes[1]])
        return out

    # Case 4: N>2 loaders, no label hints -> sequential fallback.
    apply_picks([*inline_high, *inline_low], lora_nodes)
    return out
