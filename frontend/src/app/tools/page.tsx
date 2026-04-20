'use client'

import { useState } from 'react'
import { Wand2, Maximize2, Users, Film, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Slider } from '@/components/ui/slider'

type SubmitResult = { remote_job_id?: string; est_cost_usd?: number; mode?: string; error?: string } | null

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground pt-20 pb-12">
      <div className="max-w-7xl mx-auto px-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wand2 className="w-6 h-6 text-fuchsia-400" />
            Advanced Tools
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Outpaint (extend canvas), Character Sheet (multi-view), LTX Video (fast cheap video).
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <OutpaintCard />
          <CharSheetCard />
          <LtxVideoCard />
        </div>
      </div>
    </div>
  )
}

function OutpaintCard() {
  const [imageUrl, setImageUrl] = useState('')
  const [prompt, setPrompt] = useState('full body, wide shot, detailed background, same character')
  const [negative, setNegative] = useState('')
  const [padL, setPadL] = useState(256)
  const [padR, setPadR] = useState(256)
  const [padT, setPadT] = useState(0)
  const [padB, setPadB] = useState(256)
  const [feathering, setFeathering] = useState(40)
  const [steps, setSteps] = useState(25)
  const [denoise, setDenoise] = useState(1.0)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<SubmitResult>(null)

  const submit = async () => {
    if (!imageUrl.trim() || !prompt.trim()) return
    setSubmitting(true); setResult(null)
    try {
      const res = await fetch('/api/m/outpaint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_url: imageUrl.trim(),
          prompt: prompt.trim(),
          negative: negative.trim() || undefined,
          pad_left: padL, pad_right: padR, pad_top: padT, pad_bottom: padB,
          feathering, steps, denoise,
        }),
      })
      const data = await res.json()
      if (!data?.ok) setResult({ error: data?.error || 'submit failed' })
      else setResult({ remote_job_id: data.remote_job_id, est_cost_usd: data.est_cost_usd })
    } catch (e) {
      setResult({ error: String(e) })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Maximize2 className="w-5 h-5 text-cyan-400" />
        <h2 className="font-semibold">Outpaint</h2>
      </div>
      <p className="text-xs text-muted-foreground">
        Extend canvas outward. Turn close-ups into wide/loose shots.
      </p>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Source Image URL</label>
        <Input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://... (from Gallery)" />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Prompt (what to fill outside)</label>
        <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Negative (optional)</label>
        <Input value={negative} onChange={(e) => setNegative(e.target.value)} placeholder="leave blank for default" />
      </div>

      <div className="grid grid-cols-4 gap-2">
        <div><label className="text-[10px] text-muted-foreground">Left</label><Input type="number" value={padL} onChange={(e) => setPadL(parseInt(e.target.value) || 0)} /></div>
        <div><label className="text-[10px] text-muted-foreground">Right</label><Input type="number" value={padR} onChange={(e) => setPadR(parseInt(e.target.value) || 0)} /></div>
        <div><label className="text-[10px] text-muted-foreground">Top</label><Input type="number" value={padT} onChange={(e) => setPadT(parseInt(e.target.value) || 0)} /></div>
        <div><label className="text-[10px] text-muted-foreground">Bottom</label><Input type="number" value={padB} onChange={(e) => setPadB(parseInt(e.target.value) || 0)} /></div>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Feathering: {feathering}</label>
        <Slider value={[feathering]} onValueChange={(v) => setFeathering(v[0])} min={0} max={128} step={4} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Steps: {steps}</label>
          <Slider value={[steps]} onValueChange={(v) => setSteps(v[0])} min={15} max={40} step={1} />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Denoise: {denoise.toFixed(2)}</label>
          <Slider value={[denoise]} onValueChange={(v) => setDenoise(v[0])} min={0.6} max={1.0} step={0.05} />
        </div>
      </div>

      <Button onClick={submit} disabled={submitting || !imageUrl.trim() || !prompt.trim()} className="w-full bg-cyan-500 hover:bg-cyan-600 text-white">
        {submitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Maximize2 className="w-4 h-4 mr-2" />}
        Outpaint
      </Button>
      {result?.error && <div className="text-xs text-red-400">{result.error}</div>}
      {result?.remote_job_id && (
        <div className="text-xs text-muted-foreground">
          Submitted: <code className="font-mono">{result.remote_job_id}</code> · ~${result.est_cost_usd?.toFixed(4)}
        </div>
      )}
    </div>
  )
}

function CharSheetCard() {
  const [prompt, setPrompt] = useState('')
  const [negative, setNegative] = useState('')
  const [width, setWidth] = useState(2048)
  const [height, setHeight] = useState(1024)
  const [steps, setSteps] = useState(30)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<SubmitResult>(null)

  const submit = async () => {
    if (!prompt.trim()) return
    setSubmitting(true); setResult(null)
    try {
      const res = await fetch('/api/m/character_sheet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt.trim(),
          negative: negative.trim() || undefined,
          width, height, steps,
        }),
      })
      const data = await res.json()
      if (!data?.ok) setResult({ error: data?.error || 'submit failed' })
      else setResult({ remote_job_id: data.remote_job_id, est_cost_usd: data.est_cost_usd })
    } catch (e) {
      setResult({ error: String(e) })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Users className="w-5 h-5 text-purple-400" />
        <h2 className="font-semibold">Character Sheet</h2>
      </div>
      <p className="text-xs text-muted-foreground">
        Multi-view turnaround (front/side/back) on a wide canvas. Use as IP-Adapter reference or LoRA training material.
      </p>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Character description</label>
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={6}
          placeholder="e.g. 1girl, long silver hair, blue eyes, red school uniform, detailed face"
        />
        <p className="text-[10px] text-muted-foreground">Multi-view suffix auto-added (front/side/back/turnaround)</p>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Negative (optional)</label>
        <Input value={negative} onChange={(e) => setNegative(e.target.value)} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <label className="text-[10px] text-muted-foreground">Width</label>
          <Input type="number" value={width} onChange={(e) => setWidth(parseInt(e.target.value) || 2048)} step={64} />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] text-muted-foreground">Height</label>
          <Input type="number" value={height} onChange={(e) => setHeight(parseInt(e.target.value) || 1024)} step={64} />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] text-muted-foreground">Steps: {steps}</label>
          <Slider value={[steps]} onValueChange={(v) => setSteps(v[0])} min={20} max={45} step={1} />
        </div>
      </div>

      <Button onClick={submit} disabled={submitting || !prompt.trim()} className="w-full bg-purple-500 hover:bg-purple-600 text-white">
        {submitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Users className="w-4 h-4 mr-2" />}
        Generate Sheet
      </Button>
      {result?.error && <div className="text-xs text-red-400">{result.error}</div>}
      {result?.remote_job_id && (
        <div className="text-xs text-muted-foreground">
          Submitted: <code className="font-mono">{result.remote_job_id}</code> · ~${result.est_cost_usd?.toFixed(4)}
        </div>
      )}
    </div>
  )
}

function LtxVideoCard() {
  const [prompt, setPrompt] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [negative, setNegative] = useState('')
  const [width, setWidth] = useState(768)
  const [height, setHeight] = useState(512)
  const [length, setLength] = useState(97)
  const [fps, setFps] = useState(25)
  const [steps, setSteps] = useState(30)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<SubmitResult>(null)
  const [dlInfo, setDlInfo] = useState<{ downloads?: Array<{ filename: string; size_mb_approx?: number }>; example_powershell?: string } | null>(null)

  const submit = async () => {
    if (!prompt.trim()) return
    setSubmitting(true); setResult(null)
    try {
      const res = await fetch('/api/m/ltx_video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt.trim(),
          image_url: imageUrl.trim() || undefined,
          negative: negative.trim() || undefined,
          width, height, length, fps, steps,
        }),
      })
      const data = await res.json()
      if (!data?.ok) setResult({ error: data?.error || 'submit failed' })
      else setResult({ remote_job_id: data.remote_job_id, est_cost_usd: data.est_cost_usd, mode: data.mode })
    } catch (e) {
      setResult({ error: String(e) })
    } finally {
      setSubmitting(false)
    }
  }

  const loadDlInfo = async () => {
    try {
      const res = await fetch('/api/m/ltx_dl_info')
      const data = await res.json()
      if (data?.ok) setDlInfo({ downloads: data.downloads, example_powershell: data.example_powershell })
    } catch {}
  }

  return (
    <div className="rounded-xl border border-orange-500/30 bg-orange-500/5 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Film className="w-5 h-5 text-orange-400" />
        <h2 className="font-semibold">LTX Video</h2>
      </div>
      <p className="text-xs text-muted-foreground">
        LTX 0.9.5 — fast &amp; cheap video (~4-6× cheaper than Wan). T2V or I2V. <strong>Requires model DL first.</strong>
      </p>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Prompt</label>
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder="e.g. a woman walking through a neon-lit city at night, cinematic"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Source Image URL (optional, for I2V)</label>
        <Input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="Leave blank for text-to-video" />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Negative (optional)</label>
        <Input value={negative} onChange={(e) => setNegative(e.target.value)} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <label className="text-[10px] text-muted-foreground">Width</label>
          <Input type="number" value={width} onChange={(e) => setWidth(parseInt(e.target.value) || 768)} step={32} />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] text-muted-foreground">Height</label>
          <Input type="number" value={height} onChange={(e) => setHeight(parseInt(e.target.value) || 512)} step={32} />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] text-muted-foreground">FPS</label>
          <Input type="number" value={fps} onChange={(e) => setFps(parseInt(e.target.value) || 25)} />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Frames: {length}</label>
        <Slider value={[length]} onValueChange={(v) => setLength(v[0])} min={25} max={161} step={8} />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Steps: {steps}</label>
        <Slider value={[steps]} onValueChange={(v) => setSteps(v[0])} min={20} max={45} step={1} />
      </div>

      <Button onClick={submit} disabled={submitting || !prompt.trim()} className="w-full bg-orange-500 hover:bg-orange-600 text-white">
        {submitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Film className="w-4 h-4 mr-2" />}
        {imageUrl.trim() ? 'Generate (I2V)' : 'Generate (T2V)'}
      </Button>

      {result?.error && <div className="text-xs text-red-400">{result.error}</div>}
      {result?.remote_job_id && (
        <div className="text-xs text-muted-foreground">
          Submitted ({result.mode}): <code className="font-mono">{result.remote_job_id}</code> · ~${result.est_cost_usd?.toFixed(4)}
        </div>
      )}

      <div className="pt-2 border-t border-border/40">
        <button onClick={loadDlInfo} className="text-xs text-orange-400 underline">Show model DL info</button>
        {dlInfo && (
          <div className="mt-2 space-y-1 text-[10px] font-mono text-muted-foreground">
            {dlInfo.downloads?.map((d, i) => (
              <div key={i}>• {d.filename} (~{d.size_mb_approx}MB)</div>
            ))}
            {dlInfo.example_powershell && (
              <pre className="text-[10px] whitespace-pre-wrap bg-black/40 p-2 rounded mt-1 overflow-x-auto">{dlInfo.example_powershell}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
