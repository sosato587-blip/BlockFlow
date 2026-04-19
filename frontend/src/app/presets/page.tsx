'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { BookOpen, User, RefreshCw, Trash2, Plus, Sparkles, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface Preset {
  id?: string
  name: string
  kind: 'template' | 'character'
  model: string
  prompt: string
  negative?: string
  loras?: Array<{ name: string; strength: number }>
  width: number
  height: number
  steps: number
  cfg: number
  sampler_name: string
  scheduler: string
  seed_mode: 'random' | 'fixed'
  seed_value?: number
  character_name?: string
  created_at?: string
  updated_at?: string
}

export default function PresetsPage() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'template' | 'character'>('all')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/m/presets')
      const data = await res.json()
      if (data?.ok) setPresets(data.presets || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const del = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}"?`)) return
    try {
      await fetch(`/api/m/presets/${id}`, { method: 'DELETE' })
      await load()
    } catch {}
  }

  const filtered = presets.filter((p) => filter === 'all' || p.kind === filter)

  return (
    <div className="min-h-screen bg-background text-foreground pt-20 pb-12">
      <div className="max-w-6xl mx-auto px-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <BookOpen className="w-6 h-6 text-purple-400" />
              Preset Library
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Saved generation settings. Templates = reusable configs · Characters = seed-locked identities.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={load} disabled={loading} variant="outline">
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Link href="/m">
              <Button variant="outline">
                <Plus className="w-4 h-4 mr-2" />
                New (from /m)
                <ExternalLink className="w-3 h-3 ml-1" />
              </Button>
            </Link>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex items-center gap-2 border-b border-border/40">
          {(['all', 'character', 'template'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                filter === f
                  ? 'border-purple-500 text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {f === 'all' ? 'All' : f === 'character' ? '🎭 Characters' : '📋 Templates'}
              {' '}
              <span className="text-muted-foreground text-xs">
                ({f === 'all' ? presets.length : presets.filter((p) => p.kind === f).length})
              </span>
            </button>
          ))}
        </div>

        {/* Grid of presets */}
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-border/40 bg-card/30 p-12 text-center">
            <BookOpen className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              No {filter === 'all' ? '' : filter + ' '}presets yet.
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              Create from the Generate tab in <Link href="/m" className="text-purple-400 hover:underline">/m</Link>.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {filtered.map((p) => (
              <div key={p.id} className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-2 hover:border-purple-500/40 transition-colors">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    {p.kind === 'character' ? (
                      <User className="w-4 h-4 text-orange-400" />
                    ) : (
                      <BookOpen className="w-4 h-4 text-purple-400" />
                    )}
                    <h3 className="font-medium text-sm truncate">
                      {p.character_name || p.name}
                    </h3>
                  </div>
                  <button
                    onClick={() => p.id && del(p.id, p.name)}
                    className="text-muted-foreground hover:text-red-400 shrink-0"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <Badge variant="outline" className="text-[9px]">{p.model}</Badge>
                  <Badge variant="outline" className="text-[9px]">{p.width}×{p.height}</Badge>
                  <Badge variant="outline" className="text-[9px]">{p.steps}st · CFG{p.cfg}</Badge>
                  {p.seed_mode === 'fixed' && (
                    <Badge variant="outline" className="text-[9px] border-orange-500/40 text-orange-400">
                      🎲 {p.seed_value}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 font-mono min-h-[32px]">
                  {p.prompt}
                </p>
                {p.loras && p.loras.length > 0 && (
                  <div className="text-[10px] text-muted-foreground">
                    {p.loras.length} LoRA{p.loras.length > 1 ? 's' : ''}:{' '}
                    {p.loras.map((l) => l.name.replace('.safetensors', '').slice(0, 15)).join(', ')}
                  </div>
                )}
                <div className="pt-2 border-t border-border/20 flex items-center justify-between text-[9px] text-muted-foreground/60">
                  <span>{p.sampler_name}/{p.scheduler}</span>
                  <Link
                    href={`/m?preset=${p.id}`}
                    className="text-purple-400 hover:underline"
                    title="Use this preset in mobile generator"
                  >
                    <Sparkles className="w-3 h-3 inline mr-0.5" />
                    Use
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
