/**
 * Pure helper that maps inline High / Low LoRA picks onto the detected LoRA
 * loader nodes in a parsed ComfyUI workflow. Extracted from
 * `frontend.block.tsx` so the heuristic can be unit-tested without spinning
 * up the full React harness.
 *
 * This file is the canonical source of the heuristic. The in-component copy
 * in `frontend.block.tsx` (see the block around line ~1220) should be kept
 * in sync, and eventually replaced by an import of `computeInlineLoraOverrides`
 * from here. We avoided that swap in the initial extraction pass to keep the
 * diff surgical — do it under its own commit once this module is exercised
 * by tests in CI.
 *
 * Heuristic (priority order):
 *   1. `loraNodes.length === 1`           → merge both branches, feed all picks.
 *   2. `loraNodes.length >= 2` with "high"/"low" label hints
 *                                         → split by label, order-preserve within each branch.
 *   3. `loraNodes.length === 2` without label hints
 *                                         → assume `[high, low]` by node order.
 *   4. `loraNodes.length > 2` without label hints
 *                                         → feed [...high, ...low] sequentially.
 *   5. `loraNodes.length === 0`           → no-op; caller surfaces a UI warning.
 *
 * Semantics that callers can depend on:
 *   - The function NEVER overwrites an override that's already set in
 *     `existingOverrides`. This preserves any upstream wiring / user-typed
 *     value.
 *   - `strength_model` and `strength_clip` are set to the same value per pick.
 *   - Picks beyond the available loader slots are silently dropped (the only
 *     sensible behavior given a fixed-size graph).
 */

export interface LoraPick {
  name: string;
  strength: number;
}

export interface LoraLoaderNode {
  node_id: string;
  label?: string;
}

export type OverrideMap = Record<string, string>;

/**
 * Compute the overrides to merge into the base override map for inline
 * LoRA injection. Returns ONLY the new keys — does not mutate the input.
 */
export function computeInlineLoraOverrides(params: {
  loraNodes: LoraLoaderNode[];
  inlineHigh: LoraPick[];
  inlineLow: LoraPick[];
  existingOverrides?: OverrideMap;
}): OverrideMap {
  const { loraNodes, inlineHigh, inlineLow } = params;
  const existing = params.existingOverrides ?? {};
  const out: OverrideMap = {};

  // Case 5: no loader nodes → nothing to inject.
  if (loraNodes.length === 0) return out;
  if (inlineHigh.length === 0 && inlineLow.length === 0) return out;

  const applyPicks = (picks: LoraPick[], nodes: LoraLoaderNode[]): void => {
    picks.forEach((pick, idx) => {
      const node = nodes[idx];
      if (!node) return; // more picks than slots → drop the excess
      const nameKey = `${node.node_id}.lora_name`;
      const smKey = `${node.node_id}.strength_model`;
      const scKey = `${node.node_id}.strength_clip`;
      if (existing[nameKey] === undefined && out[nameKey] === undefined) {
        out[nameKey] = pick.name;
      }
      if (existing[smKey] === undefined && out[smKey] === undefined) {
        out[smKey] = String(pick.strength);
      }
      if (existing[scKey] === undefined && out[scKey] === undefined) {
        out[scKey] = String(pick.strength);
      }
    });
  };

  if (loraNodes.length === 1) {
    // Case 1: single loader — no high/low distinction possible.
    applyPicks([...inlineHigh, ...inlineLow], loraNodes);
    return out;
  }

  const highNodes = loraNodes.filter((ln) => /high/i.test(ln.label || ""));
  const lowNodes = loraNodes.filter((ln) => /low/i.test(ln.label || ""));

  if (highNodes.length > 0 || lowNodes.length > 0) {
    // Case 2: labels usable. If only one branch matched, the unmatched
    // picks still land on any leftover unlabeled nodes (ordered).
    applyPicks(inlineHigh, highNodes.length > 0 ? highNodes : loraNodes);
    applyPicks(inlineLow, lowNodes);
    return out;
  }

  if (loraNodes.length === 2) {
    // Case 3: two nodes, no label hints — assume [high, low] by order.
    applyPicks(inlineHigh, [loraNodes[0]]);
    applyPicks(inlineLow, [loraNodes[1]]);
    return out;
  }

  // Case 4: N>2 loaders, no label hints — sequential fallback.
  applyPicks([...inlineHigh, ...inlineLow], loraNodes);
  return out;
}
