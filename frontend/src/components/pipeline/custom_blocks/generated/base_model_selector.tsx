// AUTO-GENERATED. DO NOT EDIT.
// Source: custom_blocks/base_model_selector/frontend.block.tsx
'use client'

import { useEffect, useRef, useState } from 'react'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSessionState } from '@/lib/use-session-state'
import {
  type BlockDef,
  type BlockComponentProps,
} from '@/lib/pipeline/registry'

/** Shape matching backend.base_models.family_summary(). */
interface FamilyRow {
  id: string
  label: string
  description: string
  ckpt_dir: string
  lora_count_high: number
  lora_count_low: number
  checkpoints: Array<{ filename: string; label: string; notes: string }>
}

const FAMILIES_ENDPOINT = '/api/blocks/base_model_selector/families'

/** Emitted on the `base_model` output port. Downstream blocks (lora_selector,
 *  comfy_gen) read this and filter their own dropdowns. */
export interface BaseModelSelection {
  family: string          // e.g. 'illustrious'
  family_label: string    // e.g. 'Illustrious XL (SDXL anime)'
  ckpt_dir: string        // 'checkpoints' | 'diffusion_models'
  checkpoint: string      // filename, or '' if user hasn't picked one
  checkpoint_label: string // display name, or '' if none
}

function BaseModelSelectorBlock({ blockId, setOutput, registerExecute }: BlockComponentProps) {
  const [family, setFamily] = useSessionState<string>(`block_${blockId}_family`, 'illustrious')
  const [checkpoint, setCheckpoint] = useSessionState<string>(`block_${blockId}_checkpoint`, '')
  const [rows, setRows] = useState<FamilyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [warning, setWarning] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    fetch(FAMILIES_ENDPOINT)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        if (!data?.ok || !Array.isArray(data.families)) {
          setWarning(data?.error || 'Failed to load base-model families')
          return
        }
        setRows(data.families as FamilyRow[])
        if (data.warning) setWarning(String(data.warning))
      })
      .catch((e) => !cancelled && setWarning(String(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [])

  const currentFamily = rows.find((r) => r.id === family)
  const currentCheckpoint =
    currentFamily?.checkpoints.find((c) => c.filename === checkpoint)

  // Emit selection on every change
  const prevRef = useRef<string>('')
  useEffect(() => {
    const sel: BaseModelSelection = {
      family,
      family_label: currentFamily?.label || family,
      ckpt_dir: currentFamily?.ckpt_dir || 'checkpoints',
      checkpoint,
      checkpoint_label: currentCheckpoint?.label || '',
    }
    const key = JSON.stringify(sel)
    if (key !== prevRef.current) {
      prevRef.current = key
      setOutput('base_model', sel)
    }
  }, [family, checkpoint, currentFamily, currentCheckpoint, setOutput])

  useEffect(() => {
    registerExecute(async () => {
      const sel: BaseModelSelection = {
        family,
        family_label: currentFamily?.label || family,
        ckpt_dir: currentFamily?.ckpt_dir || 'checkpoints',
        checkpoint,
        checkpoint_label: currentCheckpoint?.label || '',
      }
      setOutput('base_model', sel)
    })
  })

  // When family changes and the current checkpoint doesn't belong to it, clear it.
  useEffect(() => {
    if (!currentFamily) return
    if (checkpoint && !currentFamily.checkpoints.some((c) => c.filename === checkpoint)) {
      setCheckpoint('')
    }
  }, [family, currentFamily, checkpoint, setCheckpoint])

  return (
    <div className="space-y-3">
      {warning && (
        <p className="text-[11px] text-yellow-500">{warning}</p>
      )}

      <div className="space-y-1.5">
        <Label className="text-xs font-medium">AI Base Model</Label>
        <Select value={family} onValueChange={setFamily} disabled={loading}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder={loading ? 'Loading…' : 'Select a base model'} />
          </SelectTrigger>
          <SelectContent>
            {rows.map((row) => {
              const totalLoras = row.lora_count_high + row.lora_count_low
              return (
                <SelectItem key={row.id} value={row.id} className="text-xs">
                  <div className="flex flex-col">
                    <span>{row.label}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {row.checkpoints.length} checkpoint{row.checkpoints.length === 1 ? '' : 's'}
                      {' · '}
                      {totalLoras} LoRA{totalLoras === 1 ? '' : 's'}
                    </span>
                  </div>
                </SelectItem>
              )
            })}
          </SelectContent>
        </Select>
        {currentFamily?.description && (
          <p className="text-[10px] text-muted-foreground leading-snug">
            {currentFamily.description}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs font-medium">
          Checkpoint
          <span className="text-muted-foreground font-normal"> (optional)</span>
        </Label>
        <Select
          value={checkpoint || '__none__'}
          onValueChange={(v) => setCheckpoint(v === '__none__' ? '' : v)}
          disabled={loading || !currentFamily?.checkpoints.length}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder="(use workflow default)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__" className="text-xs">(use workflow default)</SelectItem>
            {currentFamily?.checkpoints.map((cp) => (
              <SelectItem key={cp.filename} value={cp.filename} className="text-xs">
                <div className="flex flex-col">
                  <span>{cp.label}</span>
                  <span className="text-[10px] text-muted-foreground font-mono">{cp.filename}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {currentCheckpoint?.notes && (
          <p className="text-[10px] text-muted-foreground leading-snug">
            {currentCheckpoint.notes}
          </p>
        )}
        {currentFamily && currentFamily.checkpoints.length === 0 && (
          <p className="text-[10px] text-muted-foreground leading-snug">
            No curated checkpoints registered for this family yet. Override via the
            workflow JSON or add one to <code className="font-mono">backend/base_models.py</code>.
          </p>
        )}
      </div>

      <p className="text-[10px] text-muted-foreground leading-snug">
        Wire this block&apos;s <code className="font-mono">base_model</code> output into a LoRA
        Selector to filter the LoRA list to this family.
      </p>
    </div>
  )
}

export const blockDef: BlockDef = {
  type: 'baseModelSelector',
  label: 'Base Model Selector',
  description: 'Pick the AI base model (SDXL / Illustrious / Z-Image / Wan / Flux / LTX). Filters downstream LoRA list.',
  size: 'md',
  canStart: true,
  inputs: [],
  outputs: [{ name: 'base_model', kind: 'base_model' }],
  configKeys: ['family', 'checkpoint'],
  component: BaseModelSelectorBlock,
}

