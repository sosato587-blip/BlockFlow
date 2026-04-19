'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { RefreshCw, Trash2, Plus, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface Preset {
  id?: string
  name: string
  kind: string
}

interface Schedule {
  id: string
  name: string
  preset_id?: string | null
  variation_count?: number
  cron?: string
  next_run_at?: string
  status?: string
  created_at?: string
}

const CRON_PRESETS = [
  { label: 'Daily at 2am', value: '0 2 * * *' },
  { label: 'Daily at noon', value: '0 12 * * *' },
  { label: 'Every 3 hours', value: '0 */3 * * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Weekdays 9am', value: '0 9 * * 1-5' },
  { label: 'Weekly Mon 3am', value: '0 3 * * 1' },
]

export default function SchedulesPage() {
  const [scheds, setScheds] = useState<Schedule[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [loading, setLoading] = useState(true)
  const [newOpen, setNewOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPresetId, setNewPresetId] = useState('')
  const [newCount, setNewCount] = useState(10)
  const [newCron, setNewCron] = useState('0 2 * * *')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, p] = await Promise.all([
        fetch('/api/m/schedules').then((r) => r.json()),
        fetch('/api/m/presets').then((r) => r.json()),
      ])
      if (s?.ok) setScheds((s.schedules || []).reverse())
      if (p?.ok) setPresets(p.presets || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const save = async () => {
    if (!newName.trim() || !newPresetId) return
    try {
      await fetch('/api/m/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName.trim(),
          preset_id: newPresetId,
          variation_count: newCount,
          cron: newCron,
          status: 'active',
        }),
      })
      setNewOpen(false)
      setNewName(''); setNewPresetId(''); setNewCount(10); setNewCron('0 2 * * *')
      await load()
    } catch {}
  }

  const del = async (id: string, name: string) => {
    if (!confirm(`Delete schedule "${name}"?`)) return
    try {
      await fetch(`/api/m/schedules/${id}`, { method: 'DELETE' })
      await load()
    } catch {}
  }

  return (
    <div className="min-h-screen bg-background text-foreground pt-20 pb-12">
      <div className="max-w-6xl mx-auto px-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <RefreshCw className="w-6 h-6 text-blue-400" />
              Schedules
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Define cron-scheduled generation jobs. Uses saved Presets as templates.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={load} disabled={loading} variant="outline">
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button onClick={() => setNewOpen(true)} className="bg-gradient-to-r from-blue-500 to-cyan-500 text-white">
              <Plus className="w-4 h-4 mr-2" />
              New Schedule
            </Button>
          </div>
        </div>

        {/* Warning: execution worker not yet implemented */}
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-300 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>Scheduler execution worker not yet implemented.</strong>
            {' '}Schedules you define here are stored but won&apos;t auto-run yet. Use this to plan your generation pipeline; manual trigger / worker implementation is a future phase.
          </div>
        </div>

        {/* New form */}
        {newOpen && (
          <div className="rounded-xl border border-blue-500/40 bg-blue-500/5 p-6 space-y-3">
            <h3 className="font-semibold">New Schedule</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1 col-span-2">
                <label className="text-xs text-muted-foreground">Name</label>
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Nightly Rin variations" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Preset (required)</label>
                <Select value={newPresetId} onValueChange={setNewPresetId}>
                  <SelectTrigger><SelectValue placeholder="Pick a preset" /></SelectTrigger>
                  <SelectContent>
                    {presets.length === 0 ? (
                      <SelectItem value="__none__" disabled>No presets saved yet</SelectItem>
                    ) : (
                      presets.map((p) => (
                        <SelectItem key={p.id} value={p.id || ''}>
                          {p.kind === 'character' ? '🎭 ' : '📋 '}{p.name}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Generations per run</label>
                <Input type="number" value={newCount} onChange={(e) => setNewCount(parseInt(e.target.value) || 1)} min={1} max={100} />
              </div>
              <div className="space-y-1 col-span-2">
                <label className="text-xs text-muted-foreground">Cron Expression</label>
                <Input value={newCron} onChange={(e) => setNewCron(e.target.value)} className="font-mono" />
                <div className="flex flex-wrap gap-1 mt-1">
                  {CRON_PRESETS.map((c) => (
                    <button
                      key={c.value}
                      onClick={() => setNewCron(c.value)}
                      className={`text-[10px] px-2 py-0.5 rounded border ${newCron === c.value ? 'border-blue-400 bg-blue-500/20 text-blue-200' : 'border-border/40 text-muted-foreground hover:border-foreground'}`}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Format: <code className="font-mono text-cyan-300">minute hour day month weekday</code> · Examples above
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button onClick={() => setNewOpen(false)} variant="outline">Cancel</Button>
              <Button onClick={save} disabled={!newName.trim() || !newPresetId} className="bg-blue-500 text-white">
                Save
              </Button>
            </div>
          </div>
        )}

        {/* Table */}
        {scheds.length === 0 && !loading ? (
          <div className="rounded-xl border border-border/40 bg-card/30 p-12 text-center">
            <RefreshCw className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No schedules yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {scheds.map((s) => {
              const preset = presets.find((p) => p.id === s.preset_id)
              return (
                <div key={s.id} className="rounded-lg border border-border/40 bg-card/30 p-4 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium">{s.name}</h3>
                    <div className="text-xs text-muted-foreground mt-1">
                      {preset && <>Preset: <span className="text-foreground">{preset.name}</span> · </>}
                      {s.variation_count || 1} gen/run · cron <code className="font-mono text-cyan-300">{s.cron || '—'}</code>
                    </div>
                  </div>
                  <Badge variant="outline" className={`shrink-0 ${s.status === 'active' ? 'border-emerald-500/40 text-emerald-400' : 'text-muted-foreground'}`}>
                    {s.status || 'inactive'}
                  </Badge>
                  <button onClick={() => del(s.id, s.name)} className="text-muted-foreground hover:text-red-400 shrink-0">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
