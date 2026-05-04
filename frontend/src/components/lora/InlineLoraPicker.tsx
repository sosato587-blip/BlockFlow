"use client"

/**
 * Shared inline LoRA picker (High / Low branches) used by both:
 *   - Desktop: custom_blocks/comfy_gen/frontend.block.tsx (inside a <CollapsibleSection>)
 *   - Mobile:  frontend/src/app/m/page.tsx (inline, inside GenerateTab)
 *
 * Design notes:
 *   - Persistence lives OUTSIDE this component (desktop uses useSessionState,
 *     mobile uses useState). This component only owns derived state.
 *   - The subtitle text and any collapsible wrapper are provided by the caller.
 *   - Mobile-specific "+ Add LoRA" orange accent is opt-in via `accent="orange"`.
 *   - `headerRightSlot` lets mobile inject its Refresh button without forking.
 *
 * Example (desktop):
 *   <CollapsibleSection label="LoRAs (inline)" badge={externalBadge}>
 *     <p>Filtered to {family}. Applied to detected LoRA nodes ...</p>
 *     <InlineLoraPicker
 *       family={inlineFamily}
 *       groupedOptions={inlineLoraData}
 *       highPicks={inlineHighLoras}
 *       lowPicks={inlineLowLoras}
 *       onHighPicksChange={setInlineHighLoras}
 *       onLowPicksChange={setInlineLowLoras}
 *       disabled={externalLorasConnected}
 *       disabledReason="An upstream lora_selector block is wired; inline picks are ignored."
 *       compact
 *     />
 *   </CollapsibleSection>
 *
 * Example (mobile):
 *   <InlineLoraPicker
 *     family={activeFamily}
 *     familyLabel={activeFamilyLabel}
 *     groupedOptions={loraGrouped}
 *     highPicks={highLoras}
 *     lowPicks={lowLoras}
 *     onHighPicksChange={setHighLoras}
 *     onLowPicksChange={setLowLoras}
 *     accent="orange"
 *     isLoading={loraLoading}
 *     loadingMessage="Loading LoRA list... (may take 30-60s on cold start)"
 *     errorMessage={loraFetchError ?? undefined}
 *     emptyHint='Tap "+ Add LoRA" to stack quality boosters, characters, or concepts.'
 *     headerRightSlot={
 *       <button onClick={fetchLoras} disabled={loraLoading} title="Refresh">
 *         <RefreshCw className={`w-3 h-3 ${loraLoading ? "animate-spin" : ""}`} />
 *       </button>
 *     }
 *   />
 */

import * as React from "react"
import { Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"

export interface LoraPick {
  id?: string
  name: string
  strength: number
}

export interface InlineLoraPickerProps {
  /** Active base-model family key, e.g. "illustrious". */
  family: string
  /** Optional display label for the family (used in the header counter). */
  familyLabel?: string
  /** Family-grouped available LoRA names. Shape matches the lora_selector API. */
  groupedOptions: {
    grouped_high: Record<string, string[]>
    grouped_low: Record<string, string[]>
  }

  highPicks: LoraPick[]
  lowPicks: LoraPick[]
  onHighPicksChange: (next: LoraPick[]) => void
  onLowPicksChange: (next: LoraPick[]) => void

  /** Max picks per branch (default 8). */
  maxPicksPerBranch?: number
  // Slider LoRAs (e.g. StS-Detail-Slider, body sliders) work in negative
  // strength to flip their effect. Default range -1.5..2 covers both
  // standard LoRAs (0..2) and bidirectional sliders (-1.5..1.5).
  strengthMin?: number // default -1.5
  strengthMax?: number // default 2
  strengthStep?: number // default 0.05

  /** Renders all controls read-only with an explanatory banner. */
  disabled?: boolean
  disabledReason?: string

  /** Styling hints. */
  accent?: "default" | "orange"
  /** Tighter spacing / smaller typography, suited for dense desktop block layout. */
  compact?: boolean

  /** Injected into the header's right side (e.g., mobile's Refresh button). */
  headerRightSlot?: React.ReactNode

  /** Async states — typically set on mobile which fetches options over the network. */
  isLoading?: boolean
  loadingMessage?: string
  errorMessage?: string
  emptyHint?: string
}

const NONE_VALUE = "__none__"

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID()
  }
  return String(Date.now()) + String(Math.random()).slice(2, 8)
}

export function InlineLoraPicker(props: InlineLoraPickerProps): React.ReactElement {
  const {
    family,
    familyLabel,
    groupedOptions,
    highPicks,
    lowPicks,
    onHighPicksChange,
    onLowPicksChange,
    maxPicksPerBranch = 8,
    strengthMin = -1.5,
    strengthMax = 2,
    strengthStep = 0.05,
    disabled = false,
    disabledReason,
    accent = "default",
    compact = false,
    headerRightSlot,
    isLoading = false,
    loadingMessage,
    errorMessage,
    emptyHint,
  } = props

  const highOptions = groupedOptions.grouped_high[family] ?? []
  const lowOptions = groupedOptions.grouped_low[family] ?? []
  const totalUnique = React.useMemo(
    () => new Set([...highOptions, ...lowOptions]).size,
    [highOptions, lowOptions]
  )

  const addedCount = highPicks.length + lowPicks.length
  const counter = `LoRAs (${addedCount} added, ${totalUnique} available${
    familyLabel ? ` for ${familyLabel}` : ""
  })`

  const labelClass = compact
    ? "text-[10px] font-medium text-muted-foreground"
    : "text-xs font-medium text-muted-foreground"
  const branchLabelClass = compact
    ? "text-[10px] uppercase tracking-wider text-muted-foreground"
    : "text-[11px] uppercase tracking-wider text-muted-foreground"
  const selectHeight = compact ? "h-7" : "h-8"
  const iconButtonSize = compact ? "h-6 w-6" : "h-7 w-7"
  const addButtonClass =
    accent === "orange"
      ? "border border-orange-500/30 bg-orange-500/10 text-orange-400 hover:bg-orange-500/20"
      : "border border-border/60 hover:bg-accent text-foreground"
  const addButtonSize = compact ? "text-[11px] h-6 px-2" : "text-xs h-7 px-2.5"

  const showEmptyHint =
    !isLoading && !errorMessage && addedCount === 0 && !!emptyHint

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <Label className={labelClass}>{counter}</Label>
        {headerRightSlot ? (
          <div className="flex items-center gap-1">{headerRightSlot}</div>
        ) : null}
      </div>

      {/* Disabled banner */}
      {disabled && disabledReason ? (
        <div className="rounded-md border border-muted bg-muted/40 p-2 text-[10px] text-muted-foreground">
          {disabledReason}
        </div>
      ) : null}

      {/* Loading banner */}
      {isLoading ? (
        <div className="rounded-md border border-cyan-500/30 bg-cyan-500/10 p-2 text-[10px] text-cyan-300 flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" />
          {loadingMessage ?? "Loading LoRA list..."}
        </div>
      ) : null}

      {/* Error banner */}
      {!isLoading && errorMessage ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-400">
          {errorMessage}
        </div>
      ) : null}

      {/* Empty hint */}
      {showEmptyHint ? (
        <p className="text-[10px] text-muted-foreground italic">{emptyHint}</p>
      ) : null}

      {/* High / Low branches */}
      {(["high", "low"] as const).map((branch) => {
        const picks = branch === "high" ? highPicks : lowPicks
        const setPicks = branch === "high" ? onHighPicksChange : onLowPicksChange
        const options = branch === "high" ? highOptions : lowOptions
        const branchLabel = branch === "high" ? "High Noise" : "Low Noise"
        const canAddMore = picks.length < maxPicksPerBranch
        const addDisabled = disabled || !canAddMore

        return (
          <div key={branch} className="space-y-1.5">
            <Label className={branchLabelClass}>{branchLabel}</Label>

            {picks.map((pick, i) => (
              <div
                key={pick.id ?? `${branch}-${i}`}
                className="space-y-1 rounded-md border border-border/50 p-1.5"
              >
                <div className="flex items-center gap-1.5">
                  <Select
                    value={pick.name || NONE_VALUE}
                    disabled={disabled}
                    onValueChange={(v) => {
                      const next = picks.slice()
                      next[i] = { ...pick, name: v }
                      setPicks(next)
                    }}
                  >
                    <SelectTrigger className={`flex-1 ${selectHeight} text-xs`}>
                      <SelectValue placeholder="(none)" />
                    </SelectTrigger>
                    <SelectContent className="max-h-[280px]">
                      <SelectItem value={NONE_VALUE} className="text-xs">
                        (none)
                      </SelectItem>
                      {options.map((name) => (
                        <SelectItem key={name} value={name} className="text-xs">
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={disabled}
                    onClick={() =>
                      setPicks(picks.filter((_, idx) => idx !== i))
                    }
                    className={`shrink-0 ${iconButtonSize}`}
                    aria-label={`Remove ${branchLabel} LoRA`}
                  >
                    <X className="w-3 h-3" />
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <Slider
                    value={[pick.strength]}
                    disabled={disabled}
                    onValueChange={([v]: number[]) => {
                      const next = picks.slice()
                      next[i] = { ...pick, strength: v }
                      setPicks(next)
                    }}
                    min={strengthMin}
                    max={strengthMax}
                    step={strengthStep}
                    className="flex-1"
                  />
                  <span className="text-[10px] text-muted-foreground w-10 text-right tabular-nums shrink-0">
                    {pick.strength.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}

            <button
              type="button"
              disabled={addDisabled}
              onClick={() =>
                setPicks([
                  ...picks,
                  { id: makeId(), name: NONE_VALUE, strength: 1.0 },
                ])
              }
              className={`${addButtonSize} rounded-md transition-colors disabled:opacity-40 ${addButtonClass}`}
              aria-label={`Add ${branchLabel} LoRA`}
            >
              + Add {branch === "high" ? "High" : "Low"} LoRA
            </button>
          </div>
        )
      })}
    </div>
  )
}
