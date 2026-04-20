// AUTO-GENERATED. DO NOT EDIT.
// Source: custom_blocks/wan_fun_control/frontend.block.tsx
'use client'

import { useState, useCallback, useEffect } from 'react'
import { Button } from '@/components/ui/button'
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
  type FanoutStats,
  type PollingProgressEntry,
} from '@/lib/pipeline/serverless-poller'
import {
  PORT_IMAGE,
  PORT_TEXT,
  PORT_VIDEO,
  type BlockDef,
  type BlockComponentProps,
} from '@/lib/pipeline/registry'

const ENDPOINT_KEY = 'wan_fun_control_endpoint_id'
const DEFAULT_ENDPOINT_ID = 'xio27s12llqzpa'
const RUN_ENDPOINT = '/api/blocks/wan_fun_control/run'
const STATUS_ENDPOINT_BASE = '/api/blocks/wan_fun_control/status'

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

function WanFunControlBlock({
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

  const [width, setWidth] = useSessionState(`block_${blockId}_width`, 480)
  const [height, setHeight] = useSessionState(`block_${blockId}_height`, 832)
  const [length, setLength] = useSessionState(`block_${blockId}_length`, 81)
  const [cfg, setCfg] = useSessionState(`block_${blockId}_cfg`, 1.0)
  const [shift, setShift] = useSessionState(`block_${blockId}_shift`, 8.0)
  const [steps, setSteps] = useSessionState(`block_${blockId}_steps`, 20)
  const [controlMode, setControlMode] = useSessionState<'real' | 'anime'>(`block_${blockId}_control_mode`, 'real')
  const [seedMode, setSeedMode] = useSessionState<'random' | 'fixed'>(`block_${blockId}_seed_mode`, 'random')
  const [seed, setSeed] = useSessionState(`block_${blockId}_seed`, 42)
  const [status, setStatus] = useSessionState(`block_${blockId}_status`, 'Ready')
  const [progressPercent, setProgressPercent] = useState<number | null>(null)

  const { get: getBinding } = useBlockBindings(blockId, 'wanFunControl', inputs)
  const promptBinding = getBinding('prompt')
  const imageBinding = getBinding('image')
  const videoBinding = getBinding('video')

  const isPromptWired = Boolean(promptBinding?.usesUpstreamAtRuntime)
  const localPrompt = String(promptBinding?.localValue ?? '')
  const displayPrompt = isPromptWired ? String(inputs.prompt ?? '') : localPrompt

  const isImageWired = Boolean(imageBinding?.usesUpstreamAtRuntime)
  const inputImage = String(imageBinding?.value ?? '')

  const isVideoWired = Boolean(videoBinding?.usesUpstreamAtRuntime)
  const inputVideo = String(videoBinding?.value ?? '')

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
        const url = String(job.local_video_url || job.video_url || '').trim()
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

  // Resume polling on mount
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
        const url = String(job.local_video_url || job.video_url || '').trim()
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
      setOutput('video', artifacts)
      pushStatus('Done')
      setExecutionStatus?.('completed')
    }).catch((err: unknown) => {
      pushStatus('Failed')
      setExecutionStatus?.('error', String(err))
      clearPendingServerlessRun(blockId)
    })
  }, [blockId, pushStatus, setExecutionStatus, setOutput, setStatusMessage])

  // Register execute
  useEffect(() => {
    registerExecute(async (freshInputs) => {
      const runPrompt = isPromptWired ? String(freshInputs.prompt ?? '') : localPrompt
      const runImage = isImageWired ? String(freshInputs.image ?? '') : String(imageBinding?.localValue ?? '')
      const runVideo = isVideoWired ? String(freshInputs.video ?? '') : String(videoBinding?.localValue ?? '')

      if (!runImage.trim()) throw new Error('Start image URL is required')
      if (!runVideo.trim()) throw new Error('Control video URL is required')

      setExecutionStatus?.('running')
      pushStatus('Submitting...')
      setProgressPercent(null)
      clearPendingServerlessRun(blockId)

      const res = await fetch(RUN_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint_id: endpointId,
          image_url: runImage.trim(),
          video_url: runVideo.trim(),
          prompt: runPrompt || 'anime character dancing, smooth motion, high quality',
          control_mode: controlMode,
          width,
          height,
          length,
          cfg,
          shift,
          steps,
          seed,
          seed_mode: seedMode,
        }),
      })
      if (!res.ok) throw new Error(`Submit failed: HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error(data.error ?? 'Submit failed')

      const jobId = String(data.job_ids?.[0] || '').trim()
      if (!jobId) throw new Error('No job ID returned')

      pushStatus('Polling...')
      const pending: PendingServerlessRun = {
        kind: 'wan-fun-control',
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
      setOutput('video', artifacts)
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

      {/* Start Image */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <Label className="text-xs">Start Image</Label>
          <Select
            value={imageBinding?.selectedSourceValue || MANUAL_SOURCE}
            onValueChange={(v) => imageBinding?.setSelectedSource?.(v)}
          >
            <SelectTrigger className="h-7 min-w-[170px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(imageBinding?.sourceOptions ?? []).map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!isImageWired && (
          <Input
            value={inputImage}
            onChange={(e) => imageBinding?.setLocalValue(e.target.value)}
            placeholder="https://... start image URL"
            className="h-8 text-xs"
          />
        )}
      </div>

      {/* Control Video */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <Label className="text-xs">Control Video (dance)</Label>
          <Select
            value={videoBinding?.selectedSourceValue || MANUAL_SOURCE}
            onValueChange={(v) => videoBinding?.setSelectedSource?.(v)}
          >
            <SelectTrigger className="h-7 min-w-[170px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(videoBinding?.sourceOptions ?? []).map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!isVideoWired && (
          <Input
            value={inputVideo}
            onChange={(e) => videoBinding?.setLocalValue(e.target.value)}
            placeholder="https://... control video URL"
            className="h-8 text-xs"
          />
        )}
      </div>

      {/* Control Mode */}
      <div className="space-y-1">
        <Label className="text-xs">Control Mode</Label>
        <Select value={controlMode} onValueChange={(v) => setControlMode(v as 'real' | 'anime')}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="real">Real (direct video)</SelectItem>
            <SelectItem value="anime">Anime (DWPreprocessor pose)</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground">
          {controlMode === 'anime'
            ? 'Extracts pose skeleton from video — preserves character appearance'
            : 'Uses video directly as control — output follows video appearance'}
        </p>
      </div>

      {/* Endpoint */}
      <div className="space-y-1">
        <Label className="text-xs">Endpoint ID</Label>
        <Input
          value={endpointId}
          onChange={(e) => setEndpointId(e.target.value)}
          className="h-8 text-xs"
        />
      </div>

      {/* Prompt */}
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
            placeholder="anime character dancing, smooth motion..."
            className="min-h-[160px] max-h-[480px] resize-y text-xs"
          />
        )}
      </div>

      {/* Resolution + Length */}
      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Width</Label>
          <Input type="number" min={256} step={16} value={width}
            onChange={(e) => setWidth(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Height</Label>
          <Input type="number" min={256} step={16} value={height}
            onChange={(e) => setHeight(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Frames</Label>
          <Input type="number" min={5} step={4} value={length}
            onChange={(e) => setLength(Number(e.target.value))} className="h-8 text-xs" />
        </div>
      </div>

      {/* Sampling params */}
      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">CFG</Label>
          <Input type="number" min={0.1} step={0.5} value={cfg}
            onChange={(e) => setCfg(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Shift</Label>
          <Input type="number" min={1} step={1} value={shift}
            onChange={(e) => setShift(Number(e.target.value))} className="h-8 text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Steps</Label>
          <Input type="number" min={4} step={2} value={steps}
            onChange={(e) => setSteps(Number(e.target.value))} className="h-8 text-xs" />
        </div>
      </div>

      {/* Seed */}
      <div className="grid grid-cols-2 gap-2">
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
  type: 'wanFunControl',
  label: 'Wan 2.2 Fun Control',
  description: 'Transfer dance/motion from a control video onto a start image using Wan 2.2 Fun Control',
  advanced: true,
  size: 'huge',
  canStart: false,
  inputs: [
    { name: 'image', kind: PORT_IMAGE, required: false },
    { name: 'video', kind: PORT_VIDEO, required: false },
    { name: 'prompt', kind: PORT_TEXT, required: false },
  ],
  outputs: [
    { name: 'video', kind: PORT_VIDEO },
  ],
  bindings: [
    { field: 'image', input: 'image', mode: 'upstream_or_local', allowOverride: true },
    { field: 'video', input: 'video', mode: 'upstream_or_local', allowOverride: true },
    { field: 'prompt', input: 'prompt', mode: 'upstream_or_local', allowOverride: true },
  ],
  configKeys: [
    'image', 'image_override',
    'video', 'video_override',
    'prompt', 'prompt_override',
    'control_mode',
    'width', 'height', 'length',
    'cfg', 'shift', 'steps',
    'seed_mode', 'seed',
  ],
  component: WanFunControlBlock,
}

