'use client'

import { useState, useCallback, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSessionState } from '@/lib/use-session-state'
import { ACTIVE_STATUSES } from '@/lib/types'
import type { Job, RunPodProgress } from '@/lib/types'
import { MANUAL_SOURCE, useBlockBindings } from '@/lib/pipeline/block-bindings'
import {
  clearPendingServerlessRun,
  type PendingServerlessRun,
} from '@/lib/pipeline/serverless-pending'
import {
  setPersistedBlockStatus,
  startNewPendingPoll,
  resumePendingPoll,
} from '@/lib/pipeline/serverless-poller'
import {
  PORT_IMAGE,
  PORT_TEXT,
  type BlockDef,
  type BlockComponentProps,
} from '@/lib/pipeline/registry'

const ENDPOINT_KEY = 'character_sheet_endpoint_id'
const DEFAULT_ENDPOINT_ID = 'xio27s12llqzpa'
const RUN_ENDPOINT = '/api/blocks/character_sheet/run'
const STATUS_ENDPOINT_BASE = '/api/blocks/character_sheet/status'

function formatRunPodProgress(progress: RunPodProgress | null | undefined, remoteStatus: string | null | undefined): string {
  if (!progress && remoteStatus) {
    if (remoteStatus === 'IN_QUEUE') return 'Warming up...'
    return remoteStatus
  }
  if (!progress) return 'Waiting...'
  if (progress.stage === 'inference' && progress.step != null && progress.total_steps != null) {
    const eta = progress.eta_seconds != null ? ` | eta ${Math.round(progress.eta_seconds)}s` : ''
    return `Step ${progress.step}/${progress.total_steps}${eta}`
  }
  if (progress.message) return progress.message
  return `${progress.percent ?? 0}%`
}

function CharacterSheetBlock({
  blockId,
  inputs,
  setOutput,
  registerExecute,
  setStatusMessage,
  setExecutionStatus,
}: BlockComponentProps) {
  const [endpointId, setEndpointIdRaw] = useState(() => {
    if (typeof window === 'undefined') return ''
    return localStorage.getItem(ENDPOINT_KEY) || DEFAULT_ENDPOINT_ID
  })
  const setEndpointId = useCallback((v: string) => {
    setEndpointIdRaw(v)
    localStorage.setItem(ENDPOINT_KEY, v)
  }, [])

  const [width, setWidth] = useSessionState(`block_${blockId}_width`, 2048)
  const [height, setHeight] = useSessionState(`block_${blockId}_height`, 1024)
  const [steps, setSteps] = useSessionState(`block_${blockId}_steps`, 30)
  const [cfg, setCfg] = useSessionState(`block_${blockId}_cfg`, 7.0)
  const [seedMode, setSeedMode] = useSessionState<'random' | 'fixed'>(`block_${blockId}_seed_mode`, 'random')
  const [seed, setSeed] = useSessionState(`block_${blockId}_seed`, 42)
  const [status, setStatus] = useSessionState(`block_${blockId}_status`, 'Ready')
  const [progressPercent, setProgressPercent] = useState<number | null>(null)

  const { get: getBinding } = useBlockBindings(blockId, 'characterSheet', inputs)
  const promptBinding = getBinding('prompt')

  const isPromptWired = Boolean(promptBinding?.usesUpstreamAtRuntime)
  const localPrompt = String(promptBinding?.localValue ?? '')
  const displayPrompt = isPromptWired ? String(inputs.prompt ?? '') : localPrompt

  const pushStatus = useCallback((value: string) => {
    setPersistedBlockStatus(blockId, value)
    setStatus(value)
  }, [blockId, setStatus])

  const pollPending = useCallback(async (pending: PendingServerlessRun) => {
    return startNewPendingPoll<Job, string>({
      blockId,
      pending,
      fetchStatus: async (jobId: string) => {
        const res = await fetch(`${STATUS_ENDPOINT_BASE}/${encodeURIComponent(jobId)}`)
        if (!res.ok) throw new Error(`Status request failed: HTTP ${res.status}`)
        return res.json()
      },
      getJob: (payload) => {
        if (!payload || typeof payload !== 'object') return null
        const row = payload as { job?: unknown }
        if (!row.job || typeof row.job !== 'object') return null
        return row.job as Job
      },
      getStatus: (job) => String(job.status || '').toUpperCase(),
      isActiveStatus: (s) => ACTIVE_STATUSES.includes(s as Job['status']),
      isCompletedStatus: (s) => s === 'COMPLETED' || s === 'COMPLETED_WITH_WARNING',
      getError: (job) => job.error || null,
      getArtifact: (job) => {
        const j = job as Job & { local_image_url?: string; image_url?: string }
        const url = String(j.local_image_url || j.image_url || '').trim()
        return url || null
      },
      onProgress: (_stats, progress) => {
        const activeJob = progress.find((p) => p.job && ACTIVE_STATUSES.includes(p.job.status))
        if (activeJob?.job) {
          const rp = (activeJob.job as Job & { runpod_progress?: RunPodProgress | null }).runpod_progress
          const msg = formatRunPodProgress(rp, activeJob.job.remote_status)
          pushStatus(msg)
          setStatusMessage(msg)
          if (rp?.percent != null) setProgressPercent(rp.percent)
        }
      },
    })
  }, [blockId, pushStatus, setStatusMessage])

  useEffect(() => {
    const resumed = resumePendingPoll<Job, string>({
      blockId,
      fetchStatus: async (jobId: string) => {
        const res = await fetch(`${STATUS_ENDPOINT_BASE}/${encodeURIComponent(jobId)}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      },
      getJob: (payload) => {
        if (!payload || typeof payload !== 'object') return null
        const row = payload as { job?: unknown }
        if (!row.job || typeof row.job !== 'object') return null
        return row.job as Job
      },
      getStatus: (job) => String(job.status || '').toUpperCase(),
      isActiveStatus: (s) => ACTIVE_STATUSES.includes(s as Job['status']),
      isCompletedStatus: (s) => s === 'COMPLETED' || s === 'COMPLETED_WITH_WARNING',
      getError: (job) => job.error || null,
      getArtifact: (job) => {
        const j = job as Job & { local_image_url?: string; image_url?: string }
        const url = String(j.local_image_url || j.image_url || '').trim()
        return url || null
      },
      onProgress: (_stats, progress) => {
        const activeJob = progress.find((p) => p.job && ACTIVE_STATUSES.includes(p.job.status))
        if (activeJob?.job) {
          const rp = (activeJob.job as Job & { runpod_progress?: RunPodProgress | null }).runpod_progress
          pushStatus(formatRunPodProgress(rp, activeJob.job.remote_status))
          setExecutionStatus?.('running')
        }
      },
    })
    if (!resumed) return

    setExecutionStatus?.('running')
    pushStatus('Resuming...')

    resumed.then(({ artifacts, errors }) => {
      if (artifacts.length === 0) {
        pushStatus('Failed')
        setExecutionStatus?.('error', errors.join('; '))
        return
      }
      setOutput('image', artifacts)
      pushStatus('Done')
      setExecutionStatus?.('completed')
    }).catch((err: unknown) => {
      pushStatus('Failed')
      setExecutionStatus?.('error', String(err))
      clearPendingServerlessRun(blockId)
    })
  }, [blockId, pushStatus, setExecutionStatus, setOutput, setStatusMessage])

  useEffect(() => {
    registerExecute(async (freshInputs) => {
      const runPrompt = isPromptWired ? String(freshInputs.prompt ?? '') : localPrompt
      if (!runPrompt.trim()) throw new Error('Prompt is required')

      setExecutionStatus?.('running')
      pushStatus('Submitting...')
      setProgressPercent(null)
      clearPendingServerlessRun(blockId)

      const res = await fetch(RUN_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint_id: endpointId,
          prompt: runPrompt,
          width,
          height,
          steps,
          cfg,
          seed,
          seed_mode: seedMode,
        }),
      })
      if (!res.ok) throw new Error(`Submit failed: HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error(data.error ?? 'Submit failed')

      const jobId = String(data.remote_job_id || '').trim()
      if (!jobId) throw new Error('No job ID returned')

      pushStatus('Polling...')
      const pending: PendingServerlessRun = {
        kind: 'character_sheet',
        total: 1,
        submissionFailures: 0,
        submitted: [{ idx: 0, jobId }],
        startedAt: Date.now(),
      }

      const { artifacts, errors } = await pollPending(pending)
      if (artifacts.length === 0) {
        pushStatus('Failed')
        const msg = errors.join('; ') || 'Generation failed'
        setExecutionStatus?.('error', msg)
        throw new Error(msg)
      }

      setProgressPercent(null)
      setOutput('image', artifacts)
      pushStatus('Done')
      setExecutionStatus?.('completed')
    })
  })

  return (
    <div className="space-y-3">
      {progressPercent != null && (
        <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-purple-500 transition-all duration-500 ease-out"
            style={{ width: `${Math.min(100, Math.max(0, progressPercent))}%` }}
          />
        </div>
      )}

      <div className="space-y-1">
        <Label className="text-xs">Endpoint ID</Label>
        <Input
          value={endpointId}
          onChange={(e) => setEndpointId(e.target.value)}
          className="h-8 text-xs"
        />
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <Label className="text-xs">Prompt</Label>
          <Select
            value={promptBinding?.selectedSourceValue || MANUAL_SOURCE}
            onValueChange={(v) => promptBinding?.setSelectedSource?.(v)}
          >
            <SelectTrigger className="h-7 min-w-[160px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(promptBinding?.sourceOptions ?? []).map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {isPromptWired ? (
          <div className="rounded-md border border-blue-500/20 bg-blue-500/5 px-3 py-2">
            <p className="text-xs text-muted-foreground line-clamp-3">
              {displayPrompt || <span className="italic opacity-50">From pipeline</span>}
            </p>
          </div>
        ) : (
          <Textarea
            value={displayPrompt}
            onChange={(e) => promptBinding?.setLocalValue(e.target.value)}
            placeholder="character turnaround sheet, front view, side view, 3/4 view, neutral pose..."
            className="min-h-[60px] resize-y text-xs"
          />
        )}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Width <span className="text-[10px] text-muted-foreground font-normal">(2048)</span></Label>
          <Input type="number" min={1024} step={128} value={width}
            onChange={(e) => setWidth(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Height <span className="text-[10px] text-muted-foreground font-normal">(1024)</span></Label>
          <Input type="number" min={512} step={128} value={height}
            onChange={(e) => setHeight(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Steps</Label>
          <Input type="number" min={4} step={2} value={steps}
            onChange={(e) => setSteps(Number(e.target.value))} className="h-8 text-xs" />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">CFG</Label>
          <Input type="number" min={0.1} step={0.5} value={cfg}
            onChange={(e) => setCfg(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Seed Mode</Label>
          <Select value={seedMode} onValueChange={(v) => setSeedMode(v as 'random' | 'fixed')}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="random">Random</SelectItem>
              <SelectItem value="fixed">Fixed</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Seed</Label>
          <Input type="number" value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
            disabled={seedMode !== 'fixed'} className="h-8 text-xs" />
        </div>
      </div>

      {status && status !== 'Ready' && (
        <p className="text-[11px] text-muted-foreground">{status}</p>
      )}
    </div>
  )
}

export const blockDef: BlockDef = {
  type: 'characterSheet',
  label: 'Character Sheet',
  description:
    'Wide canvas (2048x1024 default) for character turnaround / multi-view sheets. ' +
    'Prompt-only — describe the character + the layout (front, side, 3/4) and SDXL composes the sheet in one pass.',
  size: 'huge',
  canStart: false,
  inputs: [
    { name: 'prompt', kind: PORT_TEXT, required: false },
  ],
  outputs: [
    { name: 'image', kind: PORT_IMAGE },
  ],
  bindings: [
    { field: 'prompt', input: 'prompt', mode: 'upstream_or_local', allowOverride: true },
  ],
  configKeys: [
    'prompt', 'prompt_override',
    'width', 'height', 'steps', 'cfg',
    'seed_mode', 'seed',
  ],
  component: CharacterSheetBlock,
}
