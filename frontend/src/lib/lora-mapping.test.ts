import { describe, it, expect } from 'vitest'
import {
  computeInlineLoraOverrides,
  type LoraLoaderNode,
  type LoraPick,
} from './lora-mapping'

// Fixture helpers
const node = (node_id: string, label?: string): LoraLoaderNode => ({ node_id, label })
const pick = (name: string, strength = 0.8): LoraPick => ({ name, strength })

describe('computeInlineLoraOverrides', () => {
  // ------------------------------------------------------------------
  // Case 5: no loaders
  // ------------------------------------------------------------------
  it('returns empty when there are no loader nodes', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [],
      inlineHigh: [pick('a.safetensors')],
      inlineLow: [pick('b.safetensors')],
    })
    expect(out).toEqual({})
  })

  // ------------------------------------------------------------------
  // No picks
  // ------------------------------------------------------------------
  it('returns empty when there are no picks', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('1'), node('2')],
      inlineHigh: [],
      inlineLow: [],
    })
    expect(out).toEqual({})
  })

  // ------------------------------------------------------------------
  // Case 1: single loader
  // ------------------------------------------------------------------
  it('case 1 — single loader gets both high and low picks merged', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('10')],
      inlineHigh: [pick('h.safetensors', 0.7)],
      inlineLow: [pick('l.safetensors', 0.9)],
    })
    // Only one slot exists, so only the FIRST merged pick ("h") lands.
    expect(out).toEqual({
      '10.lora_name': 'h.safetensors',
      '10.strength_model': '0.7',
      '10.strength_clip': '0.7',
    })
  })

  it('case 1 — single loader with two high picks and no low picks', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('10')],
      inlineHigh: [pick('a.safetensors', 0.5), pick('b.safetensors', 0.6)],
      inlineLow: [],
    })
    // Only slot 0 fills; b is dropped (fixed graph size).
    expect(out['10.lora_name']).toBe('a.safetensors')
    expect(out['10.strength_model']).toBe('0.5')
  })

  // ------------------------------------------------------------------
  // Case 2: labeled high/low (>=2 nodes)
  // ------------------------------------------------------------------
  it('case 2 — labels drive the branch split', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [
        node('5', 'LoraLoaderModelOnly_HighNoise'),
        node('6', 'LoraLoaderModelOnly_LowNoise'),
      ],
      inlineHigh: [pick('hhh.safetensors', 0.8)],
      inlineLow: [pick('lll.safetensors', 0.3)],
    })
    expect(out['5.lora_name']).toBe('hhh.safetensors')
    expect(out['5.strength_model']).toBe('0.8')
    expect(out['6.lora_name']).toBe('lll.safetensors')
    expect(out['6.strength_model']).toBe('0.3')
  })

  it('case 2 — label match is case-insensitive', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('5', 'HIGH'), node('6', 'low_pass')],
      inlineHigh: [pick('h.safetensors')],
      inlineLow: [pick('l.safetensors')],
    })
    expect(out['5.lora_name']).toBe('h.safetensors')
    expect(out['6.lora_name']).toBe('l.safetensors')
  })

  it('case 2 — only "high" labeled: high picks go to labeled nodes, low picks to unlabeled leftovers', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [
        node('5', 'high_noise_loader'),
        node('6'),          // no label
        node('7'),          // no label
      ],
      inlineHigh: [pick('h1.safetensors')],
      inlineLow: [pick('l1.safetensors')],
    })
    expect(out['5.lora_name']).toBe('h1.safetensors')
    // lowNodes.length === 0, so applyPicks(inlineLow, lowNodes) is a no-op.
    expect(out['6.lora_name']).toBeUndefined()
    expect(out['7.lora_name']).toBeUndefined()
  })

  // ------------------------------------------------------------------
  // Case 3: exactly 2 nodes with no label hints
  // ------------------------------------------------------------------
  it('case 3 — two unlabeled nodes: [high, low] by order', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('100'), node('101')],
      inlineHigh: [pick('h.safetensors', 0.7)],
      inlineLow: [pick('l.safetensors', 0.2)],
    })
    expect(out['100.lora_name']).toBe('h.safetensors')
    expect(out['100.strength_model']).toBe('0.7')
    expect(out['101.lora_name']).toBe('l.safetensors')
    expect(out['101.strength_model']).toBe('0.2')
  })

  it('case 3 — two unlabeled nodes, only high picks set', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('100'), node('101')],
      inlineHigh: [pick('h.safetensors')],
      inlineLow: [],
    })
    expect(out['100.lora_name']).toBe('h.safetensors')
    expect(out['101.lora_name']).toBeUndefined()
  })

  // ------------------------------------------------------------------
  // Case 4: >2 unlabeled nodes → sequential fallback
  // ------------------------------------------------------------------
  it('case 4 — three unlabeled nodes: picks fill sequentially', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('1'), node('2'), node('3'), node('4')],
      inlineHigh: [pick('a.safetensors'), pick('b.safetensors')],
      inlineLow: [pick('c.safetensors')],
    })
    expect(out['1.lora_name']).toBe('a.safetensors')
    expect(out['2.lora_name']).toBe('b.safetensors')
    expect(out['3.lora_name']).toBe('c.safetensors')
    expect(out['4.lora_name']).toBeUndefined()
  })

  // ------------------------------------------------------------------
  // Existing overrides must not be clobbered
  // ------------------------------------------------------------------
  it('preserves existing overrides', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('10')],
      inlineHigh: [pick('new.safetensors', 0.5)],
      inlineLow: [],
      existingOverrides: {
        '10.lora_name': 'already_set.safetensors',
        '10.strength_model': '0.9',
      },
    })
    // These keys were already set → must not be overwritten.
    expect(out['10.lora_name']).toBeUndefined()
    expect(out['10.strength_model']).toBeUndefined()
    // strength_clip was NOT pre-set, so the heuristic may still fill it.
    expect(out['10.strength_clip']).toBe('0.5')
  })

  // ------------------------------------------------------------------
  // Strength values are stringified
  // ------------------------------------------------------------------
  it('writes strength values as strings (override map is string-valued)', () => {
    const out = computeInlineLoraOverrides({
      loraNodes: [node('1')],
      inlineHigh: [pick('a.safetensors', 1.0)],
      inlineLow: [],
    })
    expect(typeof out['1.strength_model']).toBe('string')
    expect(typeof out['1.strength_clip']).toBe('string')
  })

  // ------------------------------------------------------------------
  // Does not mutate inputs
  // ------------------------------------------------------------------
  it('does not mutate the input arrays or existingOverrides', () => {
    const nodes = [node('1'), node('2')]
    const high = [pick('a.safetensors')]
    const low = [pick('b.safetensors')]
    const existing = { '1.lora_name': 'foo' }
    computeInlineLoraOverrides({
      loraNodes: nodes,
      inlineHigh: high,
      inlineLow: low,
      existingOverrides: existing,
    })
    expect(nodes).toHaveLength(2)
    expect(high).toEqual([pick('a.safetensors')])
    expect(low).toEqual([pick('b.safetensors')])
    expect(existing).toEqual({ '1.lora_name': 'foo' })
  })
})
