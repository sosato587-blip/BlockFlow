// AUTO-GENERATED. DO NOT EDIT.
// Source: custom_blocks/lora_selector/frontend.block.tsx
'use client'

/* ============================================================================
 * 🔴 DUAL-IMPLEMENTATION WARNING — READ BEFORE EDITING
 * ----------------------------------------------------------------------------
 * このファイルはデスクトップ版のブロック実装。モバイル版には **独立した**
 * LoRA セレクタが `frontend/src/app/m/page.tsx` にある（モノリス、flat list）。
 * UX ルール（ファミリ別グループ化・Base Model 連動フィルタ等）を変更したら
 * `frontend/src/app/m/page.tsx` の LoRA 関連セクションも同期更新すること。
 * 詳細: プロジェクトルート CLAUDE.md「BlockFlow フロントエンド二重実装ルール」
 * ==========================================================================*/

import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSessionState } from '@/lib/use-session-state'
import {
  PORT_LORAS,
  type BlockDef,
  type BlockComponentProps,
} from '@/lib/pipeline/registry'
import type { LoraEntry } from '@/lib/types'

const LORAS_ENDPOINT = '/api/blocks/lora_selector/loras'

interface LoraData {
  ok: boolean
  high: string[]
  low: string[]
  grouped_high: Record<string, string[]>
  grouped_low: Record<string, string[]>
  families: Array<{
    id: string
    label: string
    description: string
    lora_count_high: number
    lora_count_low: number
  }>
  from_cache: boolean
  warning?: string
  applied_family?: string | null
}

/** Matches `BaseModelSelection` emitted by base_model_selector. */
interface BaseModelInput {
  family?: string
  family_label?: string
  checkpoint?: string
}

async function fetchLoras(refresh = false) {
  const qs = refresh ? '?refresh=1' : ''
  const res = await fetch(`${LORAS_ENDPOINT}${qs}`)
  return res.json() as Promise<LoraData>
}

interface LoraRowProps {
  grouped: Record<string, string[]>
  families: LoraData['families']
  activeFamily: string      // '' = show all, grouped
  entry: LoraEntry
  onChange: (entry: LoraEntry) => void
  onRemove: () => void
}

function LoraRow({ grouped, families, activeFamily, entry, onChange, onRemove }: LoraRowProps) {
  // Build the visible option structure.
  // If activeFamily is set: flat list of just that family.
  // Else: grouped by family (SelectGroup headers per family).
  const renderOptions = () => {
    if (activeFamily) {
      const options = grouped[activeFamily] ?? []
      return options.map((name) => (
        <SelectItem key={name} value={name} className="text-xs">
          {name}
        </SelectItem>
      ))
    }
    // Grouped — iterate families in family_summary order (already sorted).
    return families.map((fam) => {
      const options = grouped[fam.id] ?? []
      if (!options.length) return null
      return (
        <SelectGroup key={fam.id}>
          <SelectLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {fam.label}
          </SelectLabel>
          {options.map((name) => (
            <SelectItem key={name} value={name} className="text-xs">
              {name}
            </SelectItem>
          ))}
        </SelectGroup>
      )
    })
  }

  return (
    <div className="space-y-1.5 rounded-md border border-border/50 p-2">
      <div className="flex items-center gap-2">
        <Select value={entry.name} onValueChange={(v) => onChange({ ...entry, name: v })}>
          <SelectTrigger className="flex-1 min-w-0 h-8 text-xs">
            <SelectValue placeholder="(none)" />
          </SelectTrigger>
          <SelectContent className="max-h-[320px]">
            <SelectItem value="__none__" className="text-xs">(none)</SelectItem>
            {renderOptions()}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="icon" onClick={onRemove} className="shrink-0 h-7 w-7" aria-label="Remove LoRA">
          <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.5" fill="none" />
          </svg>
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Slider
          value={[entry.strength]}
          onValueChange={([v]) => onChange({ ...entry, strength: v })}
          min={0}
          max={2}
          step={0.05}
          className="flex-1"
          aria-label="LoRA strength"
        />
        <span className="text-[11px] text-muted-foreground w-8 text-right tabular-nums shrink-0">
          {entry.strength.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

function LoraSelectorBlock({ blockId, inputs, setOutput, registerExecute }: BlockComponentProps) {
  const [highLoras, setHighLoras] = useSessionState<LoraEntry[]>(`block_${blockId}_high_loras`, [])
  const [lowLoras, setLowLoras] = useSessionState<LoraEntry[]>(`block_${blockId}_low_loras`, [])
  const [loraData, setLoraData] = useState<LoraData>({
    ok: true, high: [], low: [], grouped_high: {}, grouped_low: {}, families: [], from_cache: false,
  })
  const [refreshing, setRefreshing] = useState(false)
  /** Local family override. '' = inherit from input, 'all' = explicitly show all. */
  const [familyOverride, setFamilyOverride] = useSessionState<string>(`block_${blockId}_family_override`, '')

  const baseModelInput = inputs?.base_model as BaseModelInput | undefined
  const inheritedFamily = baseModelInput?.family || ''

  // Effective filter: local override wins when set.
  // '' (blank) means "inherit from input"; 'all' means "explicitly ignore input".
  const activeFamily = useMemo(() => {
    if (familyOverride === 'all') return ''
    if (familyOverride) return familyOverride
    return inheritedFamily
  }, [familyOverride, inheritedFamily])

  const loadLoras = async (refresh: boolean) => {
    const res = await fetchLoras(refresh)
    if (!res || !Array.isArray(res.high) || !Array.isArray(res.low)) {
      setLoraData({
        ok: false, high: [], low: [],
        grouped_high: {}, grouped_low: {}, families: [],
        from_cache: false,
        warning: 'Failed loading LoRAs',
      })
      return
    }
    setLoraData({
      ok: Boolean(res.ok),
      high: res.high,
      low: res.low,
      grouped_high: res.grouped_high ?? {},
      grouped_low: res.grouped_low ?? {},
      families: res.families ?? [],
      from_cache: Boolean(res.from_cache),
      warning: res.warning,
    })
  }

  useEffect(() => {
    loadLoras(false).catch(() => {})
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadLoras(true)
    } finally {
      setRefreshing(false)
    }
  }

  const addHighLora = () => {
    setHighLoras([...highLoras, { name: '__none__', branch: 'high', strength: 1.0 }])
  }
  const addLowLora = () => {
    setLowLoras([...lowLoras, { name: '__none__', branch: 'low', strength: 1.0 }])
  }

  // When the effective family changes, detach any selected LoRA that no longer belongs.
  useEffect(() => {
    if (!activeFamily) return
    const allowedHigh = new Set(loraData.grouped_high[activeFamily] ?? [])
    const allowedLow = new Set(loraData.grouped_low[activeFamily] ?? [])
    const pruneRow = (row: LoraEntry, allowed: Set<string>): LoraEntry => {
      if (row.name === '__none__' || !row.name) return row
      return allowed.has(row.name) ? row : { ...row, name: '__none__' }
    }
    const newHigh = highLoras.map((r) => pruneRow(r, allowedHigh))
    const newLow = lowLoras.map((r) => pruneRow(r, allowedLow))
    if (JSON.stringify(newHigh) !== JSON.stringify(highLoras)) setHighLoras(newHigh)
    if (JSON.stringify(newLow) !== JSON.stringify(lowLoras)) setLowLoras(newLow)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFamily, loraData.grouped_high, loraData.grouped_low])

  const prevRef = useRef<string>('')
  useEffect(() => {
    const combined = [...highLoras, ...lowLoras].filter(
      (l) => l.name && l.name !== '__none__',
    )
    const key = JSON.stringify(combined)
    if (key !== prevRef.current) {
      prevRef.current = key
      setOutput('loras', combined)
    }
  }, [highLoras, lowLoras, setOutput])

  useEffect(() => {
    registerExecute(async () => {
      const combined = [...highLoras, ...lowLoras].filter(
        (l) => l.name && l.name !== '__none__',
      )
      setOutput('loras', combined)
    })
  })

  const activeFamilyRow = loraData.families.find((f) => f.id === activeFamily)
  const totalInScope =
    activeFamily
      ? (loraData.grouped_high[activeFamily]?.length ?? 0) +
        (loraData.grouped_low[activeFamily]?.length ?? 0)
      : loraData.high.length + loraData.low.length

  return (
    <div className="space-y-3">
      {/* Filter row */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <Label className="text-xs font-medium">Filter by base model</Label>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            aria-label="Refresh LoRA list"
            title="Refresh LoRA list"
          >
            <svg className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 8A6 6 0 1 1 8 2" strokeLinecap="round" />
              <path d="M8 0l2.5 2L8 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <Select
          value={familyOverride || (inheritedFamily ? '__inherit__' : 'all')}
          onValueChange={(v) => setFamilyOverride(v === '__inherit__' ? '' : v)}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {inheritedFamily && (
              <SelectItem value="__inherit__" className="text-xs">
                Inherit from Base Model Selector ({baseModelInput?.family_label || inheritedFamily})
              </SelectItem>
            )}
            <SelectItem value="all" className="text-xs">All families (grouped)</SelectItem>
            {loraData.families.map((fam) => (
              <SelectItem key={fam.id} value={fam.id} className="text-xs">
                {fam.label} ({fam.lora_count_high + fam.lora_count_low})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground leading-snug">
          {activeFamily
            ? <>Showing only <strong>{activeFamilyRow?.label ?? activeFamily}</strong> LoRAs ({totalInScope}).</>
            : <>Showing all {totalInScope} LoRAs, grouped by base model.</>}
        </p>
      </div>

      {loraData.warning && (
        <p className="text-[11px] text-yellow-500">{loraData.warning}</p>
      )}

      <div className="space-y-2">
        <Label className="text-xs font-medium">High Noise</Label>
        <div className="space-y-1.5">
          {highLoras.map((entry, i) => (
            <LoraRow
              key={i}
              grouped={loraData.grouped_high}
              families={loraData.families}
              activeFamily={activeFamily}
              entry={entry}
              onChange={(updated) => {
                const next = [...highLoras]
                next[i] = updated
                setHighLoras(next)
              }}
              onRemove={() => setHighLoras(highLoras.filter((_, idx) => idx !== i))}
            />
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={addHighLora} className="text-xs h-7">
          + Add High LoRA
        </Button>
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium">Low Noise</Label>
        <div className="space-y-1.5">
          {lowLoras.map((entry, i) => (
            <LoraRow
              key={i}
              grouped={loraData.grouped_low}
              families={loraData.families}
              activeFamily={activeFamily}
              entry={entry}
              onChange={(updated) => {
                const next = [...lowLoras]
                next[i] = updated
                setLowLoras(next)
              }}
              onRemove={() => setLowLoras(lowLoras.filter((_, idx) => idx !== i))}
            />
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={addLowLora} className="text-xs h-7">
          + Add Low LoRA
        </Button>
      </div>
    </div>
  )
}

export const blockDef: BlockDef = {
  type: 'loraSelector',
  label: 'LoRA Selector',
  description: 'Pick LoRA adapters with strength controls. Wire a Base Model Selector to auto-filter the list.',
  size: 'md',
  canStart: true,
  inputs: [
    { name: 'base_model', kind: 'base_model', required: false },
  ],
  outputs: [{ name: 'loras', kind: PORT_LORAS }],
  configKeys: ['high_loras', 'low_loras', 'family_override'],
  component: LoraSelectorBlock,
}

