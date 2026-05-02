'use client'

/**
 * Wan 2.2 Animate — character animation from reference image + driving video.
 *
 * ⚠️ SCAFFOLDING ONLY (2026-05-02). This file exists so the block-registry
 *    codegen has a real export to point at. The runtime path (workflow
 *    builder, RunPod dispatch, real UI controls) is implemented in a
 *    follow-up session — see ``WAN_ANIMATE_DESIGN.md`` next door for the
 *    work list and node graph analysis.
 *
 * The block is registered with ``advanced: true`` so it stays out of the
 *    default palette. To preview it, toggle advanced mode via the ``+``
 *    drawer; the placeholder UI explains where to go next.
 */

import {
  PORT_IMAGE,
  PORT_TEXT,
  PORT_VIDEO,
  type BlockDef,
  type BlockComponentProps,
} from '@/lib/pipeline/registry'

function WanAnimateBlock({ blockId }: BlockComponentProps) {
  return (
    <div className="space-y-2">
      <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2">
        <p className="text-[11px] font-medium text-amber-300">
          Wan 2.2 Animate — scaffolding only
        </p>
        <p className="text-[10px] text-amber-200/80 mt-1 leading-snug">
          The workflow builder, dispatcher, and real UI are not implemented
          yet. See <code>custom_blocks/wan_animate/WAN_ANIMATE_DESIGN.md</code>
          for the node graph analysis, required RunPod-side files, and the
          follow-up implementation plan. Block id: <code>{blockId}</code>.
        </p>
      </div>
    </div>
  )
}

export const blockDef: BlockDef = {
  type: 'wanAnimate',
  label: 'Wan 2.2 Animate (draft)',
  description:
    'Character animation: reference image + driving video -> animated character. ' +
    'Currently scaffolding — see WAN_ANIMATE_DESIGN.md.',
  size: 'lg',
  canStart: false,
  // Hides the block from the default palette; users who toggle Advanced
  // mode (the ``+`` drawer) can still drop it on the canvas to read the
  // explanatory placeholder above.
  advanced: true,
  inputs: [
    { name: 'image', kind: PORT_IMAGE, required: false },
    { name: 'video', kind: PORT_VIDEO, required: false },
    { name: 'prompt', kind: PORT_TEXT, required: false },
  ],
  outputs: [{ name: 'video', kind: PORT_VIDEO }],
  configKeys: [],
  component: WanAnimateBlock,
}
