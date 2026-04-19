'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { Heart, ImageIcon, ListTodo, RefreshCw, Star, X, ExternalLink, Sparkles, Database, Loader2, CheckCircle2, AlertCircle, Repeat, Square, Save, BookOpen, DollarSign, Trash2, User, GitCompareArrows, Layers } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  fetchRuns,
  toggleRunFavorite,
} from '@/lib/api'

// R2 image type (kept locally to avoid dependency on uncommitted lib changes).
interface R2Image {
  key: string
  filename: string
  size: number
  last_modified: string
  url: string
}

// R2 image fetcher with graceful 404 handling (works whether or not r2_routes
// has been committed to backend).
async function fetchR2Images(
  limit = 50,
  offset = 0,
  prefix = ''
): Promise<{ ok: boolean; items?: R2Image[]; total?: number; error?: string }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (prefix) params.set('prefix', prefix)
  try {
    const res = await fetch(`/api/r2/list?${params}`)
    if (res.status === 404) {
      return { ok: false, error: 'R2 endpoint not configured (backend missing /api/r2/list)' }
    }
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` }
    }
    return res.json()
  } catch (e) {
    return { ok: false, error: String(e) }
  }
}

// ============================================================
// Types
// ============================================================
type TabId = 'generate' | 'gallery' | 'favorites' | 'queue' | 'models' | 'batch' | 'publications' | 'schedules'

interface RunRecord {
  id: string
  name?: string
  status?: string
  created_at?: string | number
  favorited?: boolean | number
  duration_ms?: number
}

// ============================================================
// Top-level page
// ============================================================
const TABS: { id: TabId; label: string; Icon: typeof ImageIcon }[] = [
  { id: 'generate', label: 'Gen', Icon: Sparkles },
  { id: 'batch', label: 'Batch', Icon: Layers },
  { id: 'gallery', label: 'Gallery', Icon: ImageIcon },
  { id: 'favorites', label: 'Favs', Icon: Heart },
  { id: 'queue', label: 'Queue', Icon: ListTodo },
  { id: 'publications', label: 'Pub', Icon: Save },
  { id: 'schedules', label: 'Sched', Icon: RefreshCw },
  { id: 'models', label: 'Models', Icon: Database },
]

export default function MobilePage() {
  const [tab, setTab] = useState<TabId>('generate')
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <Header />
      <TabBar current={tab} onChange={setTab} />
      <main className="flex-1 overflow-y-auto pb-24">
        {tab === 'generate' && <GenerateTab />}
        {tab === 'batch' && <BatchTab />}
        {tab === 'gallery' && <GalleryTab />}
        {tab === 'favorites' && <FavoritesTab />}
        {tab === 'queue' && <QueueTab />}
        {tab === 'publications' && <PublicationsTab />}
        {tab === 'schedules' && <SchedulesTab />}
        {tab === 'models' && <ModelsTab />}
      </main>
      <BottomLink />
    </div>
  )
}

// ============================================================
// Header
// ============================================================
function Header() {
  const [cost, setCost] = useState<CostSummary | null>(null)

  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        const res = await fetch('/api/m/cost')
        const data = await res.json()
        if (mounted && data?.ok) setCost(data)
      } catch {}
    }
    void load()
    const t = setInterval(load, 30000)  // refresh every 30s
    return () => { mounted = false; clearInterval(t) }
  }, [])

  return (
    <header className="sticky top-0 z-20 border-b border-border/40 bg-background/85 backdrop-blur-md px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-orange-400 to-pink-500 flex items-center justify-center shrink-0">
            <span className="text-white text-[10px] font-bold">BF</span>
          </div>
          <h1 className="text-base font-semibold tracking-tight">BlockFlow</h1>
          <Badge variant="outline" className="text-[9px] uppercase tracking-wider px-1.5 py-0 h-4">
            mobile
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {cost && (
            <div
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md bg-card/60 border border-border/40"
              title={`Today: $${cost.today_usd.toFixed(3)} (${cost.today_count} gen) · Month: $${cost.month_usd.toFixed(3)}`}
            >
              <DollarSign className="w-2.5 h-2.5 text-emerald-400" />
              <span className="font-mono">{cost.today_usd.toFixed(2)}</span>
              <span className="text-muted-foreground">today</span>
            </div>
          )}
          <Link
            href="/generate"
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors hidden sm:flex items-center gap-1"
          >
            Desktop <ExternalLink className="w-3 h-3" />
          </Link>
        </div>
      </div>
    </header>
  )
}

// ============================================================
// TabBar
// ============================================================
function TabBar({ current, onChange }: { current: TabId; onChange: (id: TabId) => void }) {
  return (
    <nav className="sticky top-[57px] z-10 border-b border-border/40 bg-background/85 backdrop-blur-md overflow-x-auto scrollbar-hide">
      <div className="flex min-w-full">
        {TABS.map(({ id, label, Icon }) => {
          const active = current === id
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className={`relative flex flex-col items-center justify-center gap-0.5 py-2.5 px-4 text-[10px] font-medium transition-colors shrink-0 flex-1 min-w-[65px] ${
                active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{label}</span>
              {active && (
                <span className="absolute bottom-0 left-1/4 right-1/4 h-0.5 rounded-t-full bg-gradient-to-r from-orange-400 to-pink-500" />
              )}
            </button>
          )
        })}
      </div>
    </nav>
  )
}

// ============================================================
// Gallery Tab
// ============================================================
function GalleryTab() {
  const [images, setImages] = useState<R2Image[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<R2Image | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchR2Images(60, 0, '')
      if (res.ok) {
        setImages(res.items || [])
      } else {
        setError(res.error || 'Failed to load')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="px-3 py-3">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          {loading ? 'Loading...' : `${images.length} items`}
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={load}
          disabled={loading}
          className="h-7 px-2 text-xs"
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 mb-3">
          {error}
        </div>
      )}

      {loading && images.length === 0 ? (
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-square rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : images.length === 0 ? (
        <EmptyState
          icon={<ImageIcon className="w-8 h-8" />}
          message={
            error?.includes('R2 endpoint not configured')
              ? 'R2 gallery backend not available yet. Use Queue tab for run history.'
              : 'No images yet. Generate something first.'
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {images.map((img) => (
            <button
              key={img.key}
              onClick={() => setSelected(img)}
              className="relative aspect-square rounded-lg overflow-hidden bg-card border border-border/40 hover:border-orange-400/60 transition-colors"
            >
              {isVideo(img.filename) ? (
                <div className="absolute inset-0 flex items-center justify-center bg-card/50 text-muted-foreground text-[10px]">
                  🎬 video
                </div>
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={img.url}
                  alt={img.filename}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              )}
              <div className="absolute bottom-0 inset-x-0 px-1.5 py-1 bg-gradient-to-t from-black/80 to-transparent">
                <div className="text-[9px] text-white/90 truncate font-mono">
                  {img.filename.split('/').pop()}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      <ImageModal image={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

// ============================================================
// Favorites Tab
// ============================================================
function FavoritesTab() {
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchRuns(50, 0, true)
      const items: RunRecord[] = (res?.runs || []) as RunRecord[]
      setRuns(Array.isArray(items) ? items : [])
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const toggleFav = useCallback(
    async (id: string) => {
      try {
        await toggleRunFavorite(id)
        await load()
      } catch (e) {
        console.error('toggle favorite failed', e)
      }
    },
    [load]
  )

  return (
    <div className="px-3 py-3">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          {loading ? 'Loading...' : `${runs.length} favorites`}
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={load}
          disabled={loading}
          className="h-7 px-2 text-xs"
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 mb-3">
          {error}
        </div>
      )}
      {loading && runs.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          icon={<Star className="w-8 h-8" />}
          message="No favorites yet. Star runs you want to keep."
        />
      ) : (
        <ul className="space-y-2">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} onToggleFav={() => toggleFav(run.id)} />
          ))}
        </ul>
      )}
    </div>
  )
}

// ============================================================
// Queue Tab
// ============================================================
function QueueTab() {
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchRuns(30, 0, false)
      const items: RunRecord[] = (res?.runs || []) as RunRecord[]
      setRuns(Array.isArray(items) ? items : [])
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Auto-refresh queue every 8s
  useEffect(() => {
    const t = setInterval(() => void load(), 8000)
    return () => clearInterval(t)
  }, [load])

  const toggleFav = useCallback(
    async (id: string) => {
      try {
        await toggleRunFavorite(id)
        await load()
      } catch (e) {
        console.error('toggle favorite failed', e)
      }
    },
    [load]
  )

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const r of runs) {
      const k = (r.status || 'unknown').toLowerCase()
      c[k] = (c[k] || 0) + 1
    }
    return c
  }, [runs])

  return (
    <div className="px-3 py-3">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          {loading ? 'Loading...' : `${runs.length} runs`}
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={load}
          disabled={loading}
          className="h-7 px-2 text-xs"
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {Object.keys(counts).length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {Object.entries(counts).map(([status, count]) => (
            <Badge key={status} variant="outline" className="text-[10px] capitalize">
              {status}: {count}
            </Badge>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 mb-3">
          {error}
        </div>
      )}

      {loading && runs.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-16 rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          icon={<ListTodo className="w-8 h-8" />}
          message="Queue is empty."
        />
      ) : (
        <ul className="space-y-2">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} onToggleFav={() => toggleFav(run.id)} />
          ))}
        </ul>
      )}
    </div>
  )
}

// ============================================================
// Reusable: RunCard
// ============================================================
function RunCard({ run, onToggleFav }: { run: RunRecord; onToggleFav: () => void }) {
  const status = (run.status || 'unknown').toLowerCase()
  const statusColor =
    status === 'completed' ? 'text-emerald-400' :
    status === 'failed' || status === 'error' ? 'text-red-400' :
    status === 'cancelled' ? 'text-muted-foreground' :
    status === 'in_progress' || status === 'running' ? 'text-blue-400' :
    'text-amber-400'

  const block = run.name || 'unknown'
  const createdRaw = run.created_at
  const created = createdRaw
    ? typeof createdRaw === 'number'
      ? new Date(createdRaw * 1000).toLocaleString()
      : new Date(createdRaw).toLocaleString()
    : '—'
  const isFav = !!run.favorited

  return (
    <li className="rounded-lg border border-border/40 bg-card/40 p-3 flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-[10px] font-mono uppercase ${statusColor}`}>
            {status}
          </span>
          <span className="text-[10px] text-muted-foreground truncate">{block}</span>
        </div>
        <div className="text-[10px] text-muted-foreground/70 font-mono truncate">
          {run.id.slice(0, 8)}
        </div>
        <div className="text-[10px] text-muted-foreground/70">
          {created}
        </div>
      </div>
      <button
        onClick={onToggleFav}
        className="shrink-0 h-8 w-8 rounded-lg flex items-center justify-center hover:bg-accent/40 transition-colors"
        aria-label="Toggle favorite"
      >
        <Star
          className={`w-4 h-4 transition-colors ${
            isFav ? 'fill-orange-400 text-orange-400' : 'text-muted-foreground'
          }`}
        />
      </button>
    </li>
  )
}

// ============================================================
// Image Modal
// ============================================================
function ImageModal({ image, onClose }: { image: R2Image | null; onClose: () => void }) {
  const open = image !== null
  const isVid = image ? isVideo(image.filename) : false
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[95vw] max-h-[90vh] p-0 overflow-hidden gap-0">
        <DialogTitle className="sr-only">{image?.filename || 'Image preview'}</DialogTitle>
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 h-8 w-8 rounded-full bg-background/70 backdrop-blur-md flex items-center justify-center hover:bg-background"
        >
          <X className="w-4 h-4" />
        </button>
        {image && (
          <div className="bg-black flex items-center justify-center min-h-[50vh]">
            {isVid ? (
              <video src={image.url} controls className="max-w-full max-h-[80vh]" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image.url} alt={image.filename} className="max-w-full max-h-[80vh] object-contain" />
            )}
          </div>
        )}
        {image && (
          <div className="px-4 py-3 border-t border-border/40 bg-card text-[10px] font-mono space-y-0.5">
            <div className="truncate">{image.filename}</div>
            <div className="text-muted-foreground">
              {formatSize(image.size)} · {new Date(image.last_modified).toLocaleString()}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ============================================================
// Reusable: EmptyState
// ============================================================
function EmptyState({ icon, message }: { icon: React.ReactNode; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
      <div className="mb-3 opacity-40">{icon}</div>
      <p className="text-xs">{message}</p>
    </div>
  )
}

// ============================================================
// BottomLink (footer)
// ============================================================
function BottomLink() {
  return (
    <footer className="fixed bottom-0 inset-x-0 z-10 border-t border-border/40 bg-background/85 backdrop-blur-md px-4 py-2">
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span className="font-mono">BlockFlow Mobile</span>
        <Link
          href="/generate"
          className="flex items-center gap-1 hover:text-foreground transition-colors"
        >
          Open Editor <ExternalLink className="w-3 h-3" />
        </Link>
      </div>
    </footer>
  )
}

// ============================================================
// Batch Tab — prompt variations (bulk generation)
// ============================================================

interface BatchJob {
  variation_index: number
  remote_job_id: string
  status: string
  prompt?: string
  output_url?: string
  est_cost_usd?: number
  last_error?: string
}

interface BatchRecord {
  id: string
  name: string
  preset_id?: string | null
  base?: Record<string, unknown>
  variations?: Array<Record<string, unknown>>
  jobs?: BatchJob[]
  status?: string
  created_at?: string
  errors?: string[] | null
}

function BatchTab() {
  const [batches, setBatches] = useState<BatchRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [newOpen, setNewOpen] = useState(false)
  const [presets, setPresets] = useState<Preset[]>([])
  const [newPresetId, setNewPresetId] = useState('')
  const [newOverlays, setNewOverlays] = useState('')  // one per line
  const [newName, setNewName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [bRes, pRes] = await Promise.all([
        fetch('/api/m/batches'),
        fetch('/api/m/presets'),
      ])
      const b = await bRes.json()
      const p = await pRes.json()
      if (b?.ok) setBatches((b.batches || []).reverse())
      if (p?.ok) setPresets(p.presets || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  // Auto-poll active batches
  useEffect(() => {
    const hasActive = batches.some((b) =>
      b.status === 'running' || b.status === 'submitting'
    )
    if (!hasActive) return
    const t = setInterval(async () => {
      for (const b of batches) {
        if (b.status === 'running' || b.status === 'submitting') {
          try {
            const res = await fetch(`/api/m/batch/${b.id}`)
            const data = await res.json()
            if (data?.ok) {
              setBatches((prev) => prev.map((x) => x.id === b.id ? data.batch : x))
            }
          } catch {}
        }
      }
    }, 6000)
    return () => clearInterval(t)
  }, [batches])

  const submitBatch = async () => {
    const preset = presets.find((p) => p.id === newPresetId)
    if (!preset) {
      setError('Select a preset as base')
      return
    }
    const overlays = newOverlays
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
    if (overlays.length === 0) {
      setError('Add at least 1 variation (one prompt_overlay per line)')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const base = {
        model: preset.model,
        prompt: preset.prompt,
        negative: preset.negative,
        loras: preset.loras,
        width: preset.width, height: preset.height,
        steps: preset.steps, cfg: preset.cfg,
        sampler_name: preset.sampler_name,
        scheduler: preset.scheduler,
      }
      const variations = overlays.map((o) => ({ prompt_overlay: o }))
      const res = await fetch('/api/m/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName || `${preset.name} × ${overlays.length}`,
          preset_id: preset.id,
          base, variations,
        }),
      })
      const data = await res.json()
      if (!data?.ok) {
        setError(data?.error || 'batch failed')
        return
      }
      setNewOpen(false)
      setNewName('')
      setNewOverlays('')
      setNewPresetId('')
      await load()
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const deleteBatch = async (id: string) => {
    if (!confirm('Delete this batch record? (Generated images stay in Gallery)')) return
    try {
      await fetch(`/api/m/batch/${id}`, { method: 'DELETE' })
      await load()
    } catch {}
  }

  return (
    <div className="px-3 py-3 space-y-3">
      {!newOpen ? (
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">
            {loading ? 'Loading...' : `${batches.length} batches`}
          </h2>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="h-7 px-2 text-xs">
              <RefreshCw className={`w-3 h-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button
              onClick={() => setNewOpen(true)}
              size="sm"
              className="h-7 px-3 text-xs bg-gradient-to-r from-orange-500 to-pink-500 text-white"
            >
              + New
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-orange-500/40 bg-orange-500/5 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-orange-300">New Batch</span>
            <button onClick={() => { setNewOpen(false); setError(null) }} className="text-muted-foreground hover:text-red-400">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium text-muted-foreground">Base Preset (required)</label>
            <Select value={newPresetId} onValueChange={setNewPresetId}>
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder="(pick a preset first)" />
              </SelectTrigger>
              <SelectContent>
                {presets.length === 0 ? (
                  <SelectItem value="__none__" disabled className="text-xs">
                    No presets yet — save one from Generate tab first
                  </SelectItem>
                ) : (
                  presets.map((p) => (
                    <SelectItem key={p.id} value={p.id || ''} className="text-xs">
                      {p.kind === 'character' ? '🎭 ' : '📋 '}{p.name}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium text-muted-foreground">
              Variations (one prompt_overlay per line)
            </label>
            <Textarea
              value={newOverlays}
              onChange={(e) => setNewOverlays(e.target.value)}
              placeholder={`white summer dress, park, sunny\nred cocktail dress, rooftop bar, night\nkimono, temple, autumn leaves\n...`}
              className="min-h-[120px] text-xs font-mono"
            />
            <p className="text-[9px] text-muted-foreground">
              Each line becomes a variation appended to the preset&apos;s base prompt.
              Est. total: ${(presets.find((p) => p.id === newPresetId)?.model === 'z_image' ? 0.04 : 0.04) * newOverlays.split('\n').filter((l) => l.trim()).length}
            </p>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium text-muted-foreground">Batch name (optional)</label>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. 'Rin variations for cafe series'"
              className="h-8 text-xs"
            />
          </div>
          {error && <div className="text-[10px] text-red-400">{error}</div>}
          <Button
            onClick={submitBatch}
            disabled={submitting || !newPresetId || !newOverlays.trim()}
            className="w-full h-10 text-xs bg-gradient-to-r from-orange-500 to-pink-500 text-white"
          >
            {submitting ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" />Submitting...</> : <><Sparkles className="w-3 h-3 mr-1" />Submit Batch</>}
          </Button>
        </div>
      )}

      {!loading && batches.length === 0 && !newOpen && (
        <EmptyState icon={<Layers className="w-8 h-8" />} message="No batches yet. Tap + New to generate multiple variations." />
      )}

      <div className="space-y-2">
        {batches.map((b) => {
          const jobs = b.jobs || []
          const done = jobs.filter((j) => j.status === 'COMPLETED').length
          const failed = jobs.filter((j) => ['FAILED', 'CANCELLED', 'TIMED_OUT'].includes(j.status)).length
          const running = jobs.length - done - failed
          const isExpanded = expandedId === b.id

          return (
            <div key={b.id} className="rounded-lg border border-border/40 bg-card/30 overflow-hidden">
              <button
                onClick={() => setExpandedId(isExpanded ? null : b.id)}
                className="w-full flex items-center justify-between p-3 hover:bg-card/50 transition-colors text-left"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">{b.name}</div>
                  <div className="text-[10px] text-muted-foreground font-mono">
                    {done}/{jobs.length} done {failed > 0 && `(${failed} failed)`} · {b.status}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {running > 0 && <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />}
                  <span className={`transition-transform ${isExpanded ? 'rotate-90' : ''}`}>›</span>
                </div>
              </button>
              {isExpanded && (
                <div className="border-t border-border/40 p-3 space-y-2">
                  <div className="grid grid-cols-3 gap-1.5">
                    {jobs.map((j, i) => {
                      const isDone = j.status === 'COMPLETED' && j.output_url
                      return (
                        <div key={j.remote_job_id} className="aspect-[9/16] rounded-md overflow-hidden bg-card border border-border/40 relative">
                          <div className="absolute top-1 left-1 z-10 text-[9px] font-bold text-white bg-black/60 px-1 rounded">
                            {i + 1}
                          </div>
                          {isDone ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={j.output_url} alt={`var ${i}`} className="w-full h-full object-cover" loading="lazy" />
                          ) : (
                            <div className="flex items-center justify-center h-full text-[9px] text-muted-foreground">
                              {j.status}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                  <button
                    onClick={() => deleteBatch(b.id)}
                    className="text-[10px] text-red-400 hover:underline"
                  >
                    Delete batch record
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================================
// Publications Tab — track where images are published
// ============================================================

interface Publication {
  id: string
  name?: string
  image_url: string
  title?: string
  description?: string
  platforms?: Array<{ platform: string; status: string; url?: string; published_at?: string }>
  tags?: string[]
  notes?: string
  created_at?: string
}

function PublicationsTab() {
  const [pubs, setPubs] = useState<Publication[]>([])
  const [loading, setLoading] = useState(true)
  const [newOpen, setNewOpen] = useState(false)
  const [newImageUrl, setNewImageUrl] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [newPlatform, setNewPlatform] = useState('fanvue')
  const [newStatus, setNewStatus] = useState('draft')
  const [newNotes, setNewNotes] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/m/publications')
      const data = await res.json()
      if (data?.ok) setPubs((data.publications || []).reverse())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const save = async () => {
    if (!newImageUrl.trim()) return
    const body: Partial<Publication> = {
      image_url: newImageUrl.trim(),
      title: newTitle,
      notes: newNotes,
      platforms: [{ platform: newPlatform, status: newStatus }],
    }
    try {
      await fetch('/api/m/publications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setNewOpen(false)
      setNewImageUrl('')
      setNewTitle('')
      setNewNotes('')
      await load()
    } catch {}
  }

  const del = async (id: string) => {
    if (!confirm('Delete publication record?')) return
    try {
      await fetch(`/api/m/publications/${id}`, { method: 'DELETE' })
      await load()
    } catch {}
  }

  return (
    <div className="px-3 py-3 space-y-3">
      {!newOpen ? (
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">
            {loading ? 'Loading...' : `${pubs.length} publications`}
          </h2>
          <Button onClick={() => setNewOpen(true)} size="sm" className="h-7 px-3 text-xs bg-gradient-to-r from-emerald-500 to-teal-500 text-white">
            + Add
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-emerald-300">New Publication</span>
            <button onClick={() => setNewOpen(false)}><X className="w-4 h-4 text-muted-foreground" /></button>
          </div>
          <Input value={newImageUrl} onChange={(e) => setNewImageUrl(e.target.value)} placeholder="Image URL (from Gallery)" className="h-8 text-xs" />
          <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Title / caption" className="h-8 text-xs" />
          <div className="grid grid-cols-2 gap-2">
            <Select value={newPlatform} onValueChange={setNewPlatform}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {['fanvue', 'dlsite', 'patreon', 'fanbox', 'boosty', 'twitter', 'other'].map((p) => (
                  <SelectItem key={p} value={p} className="text-xs">{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={newStatus} onValueChange={setNewStatus}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {['draft', 'scheduled', 'published'].map((s) => (
                  <SelectItem key={s} value={s} className="text-xs">{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Textarea value={newNotes} onChange={(e) => setNewNotes(e.target.value)} placeholder="Notes (optional)" className="min-h-[50px] text-xs" />
          <Button onClick={save} disabled={!newImageUrl.trim()} className="w-full h-9 text-xs bg-emerald-500 text-white">Save</Button>
        </div>
      )}

      {!loading && pubs.length === 0 && !newOpen && (
        <EmptyState icon={<Save className="w-8 h-8" />} message="No publications tracked yet. Tap + Add after publishing." />
      )}

      <ul className="space-y-2">
        {pubs.map((p) => (
          <li key={p.id} className="rounded-lg border border-border/40 bg-card/30 p-3 flex items-start gap-3">
            <div className="h-16 w-12 shrink-0 rounded overflow-hidden bg-card">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {p.image_url && <img src={p.image_url} alt="" className="w-full h-full object-cover" loading="lazy" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{p.title || '(untitled)'}</div>
              <div className="flex flex-wrap gap-1 mt-1">
                {(p.platforms || []).map((pl, i) => (
                  <Badge key={i} variant="outline" className="text-[9px] px-1.5 py-0">
                    {pl.platform} · {pl.status}
                  </Badge>
                ))}
              </div>
              {p.notes && <div className="text-[10px] text-muted-foreground mt-1 line-clamp-2">{p.notes}</div>}
            </div>
            <button onClick={() => del(p.id)} className="shrink-0 text-muted-foreground hover:text-red-400">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ============================================================
// Schedules Tab — define schedules (execution worker not yet implemented)
// ============================================================

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

function SchedulesTab() {
  const [scheds, setScheds] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(true)
  const [newOpen, setNewOpen] = useState(false)
  const [presets, setPresets] = useState<Preset[]>([])
  const [newName, setNewName] = useState('')
  const [newPresetId, setNewPresetId] = useState('')
  const [newCount, setNewCount] = useState(10)
  const [newCron, setNewCron] = useState('0 2 * * *')  // every day at 2am

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [sRes, pRes] = await Promise.all([
        fetch('/api/m/schedules'),
        fetch('/api/m/presets'),
      ])
      const s = await sRes.json()
      const p = await pRes.json()
      if (s?.ok) setScheds((s.schedules || []).reverse())
      if (p?.ok) setPresets(p.presets || [])
    } catch {} finally { setLoading(false) }
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

  const del = async (id: string) => {
    if (!confirm('Delete schedule?')) return
    try {
      await fetch(`/api/m/schedules/${id}`, { method: 'DELETE' })
      await load()
    } catch {}
  }

  return (
    <div className="px-3 py-3 space-y-3">
      <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-300">
        ⚠ Scheduler execution worker not yet implemented. This UI saves schedule definitions only; they won&apos;t auto-run yet.
      </div>

      {!newOpen ? (
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">
            {loading ? 'Loading...' : `${scheds.length} schedules`}
          </h2>
          <Button onClick={() => setNewOpen(true)} size="sm" className="h-7 px-3 text-xs bg-gradient-to-r from-blue-500 to-cyan-500 text-white">
            + Add
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border border-blue-500/40 bg-blue-500/5 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-blue-300">New Schedule</span>
            <button onClick={() => setNewOpen(false)}><X className="w-4 h-4 text-muted-foreground" /></button>
          </div>
          <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Schedule name" className="h-8 text-xs" />
          <Select value={newPresetId} onValueChange={setNewPresetId}>
            <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Pick a preset" /></SelectTrigger>
            <SelectContent>
              {presets.map((p) => (
                <SelectItem key={p.id} value={p.id || ''} className="text-xs">
                  {p.kind === 'character' ? '🎭 ' : '📋 '}{p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] text-muted-foreground">Count / run</label>
              <Input type="number" value={newCount} onChange={(e) => setNewCount(parseInt(e.target.value) || 1)} className="h-8 text-xs" min={1} max={50} />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-muted-foreground">Cron</label>
              <Input value={newCron} onChange={(e) => setNewCron(e.target.value)} className="h-8 text-xs font-mono" placeholder="0 2 * * *" />
            </div>
          </div>
          <p className="text-[9px] text-muted-foreground">
            Cron format: &quot;min hour day month weekday&quot;. Examples: &quot;0 2 * * *&quot; = daily 2am · &quot;0 */3 * * *&quot; = every 3 hours
          </p>
          <Button onClick={save} disabled={!newName.trim() || !newPresetId} className="w-full h-9 text-xs bg-blue-500 text-white">Save</Button>
        </div>
      )}

      {!loading && scheds.length === 0 && !newOpen && (
        <EmptyState icon={<RefreshCw className="w-8 h-8" />} message="No schedules yet. Create one after saving a preset." />
      )}

      <ul className="space-y-2">
        {scheds.map((s) => {
          const preset = presets.find((p) => p.id === s.preset_id)
          return (
            <li key={s.id} className="rounded-lg border border-border/40 bg-card/30 p-3 flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{s.name}</div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  {preset && <>Preset: {preset.name} · </>}
                  {s.variation_count || 1} gen/run · cron <code className="font-mono text-[9px] text-cyan-300">{s.cron || '—'}</code>
                </div>
              </div>
              <Badge variant="outline" className={`text-[9px] shrink-0 ${s.status === 'active' ? 'text-emerald-400 border-emerald-500/40' : 'text-muted-foreground'}`}>
                {s.status || 'inactive'}
              </Badge>
              <button onClick={() => del(s.id)} className="shrink-0 text-muted-foreground hover:text-red-400">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ============================================================
// Generate Tab — quick image generation (mobile-first form)
// ============================================================

type ModelKind = 'z_image' | 'illustrious' | 'wan_i2v'

interface InventoryFile {
  filename: string
  size_mb?: number
}

interface InventoryResp {
  ok: boolean
  inventory?: Record<string, InventoryFile[]>
  totals?: Record<string, { count: number; size_mb: number }>
  grand_total?: { files: number; size_mb: number }
  errors?: Record<string, string> | null
}

interface GenJob {
  remote_job_id: string
  status: string
  output?: { url?: string; [k: string]: unknown }
  error?: string
}

interface Preset {
  id?: string
  name: string
  kind: 'template' | 'character'
  model: ModelKind
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
  tags?: string[]
  character_name?: string
  created_at?: string
  updated_at?: string
}

interface CostSummary {
  ok: boolean
  total_usd: number
  total_count: number
  today_usd: number
  today_count: number
  month_usd: number
  month_count: number
  by_model: Record<string, { usd: number; count: number }>
}

const PROMPT_PRESETS: Record<ModelKind, { label: string; text: string }[]> = {
  z_image: [
    { label: 'Real woman portrait', text: '1girl, beautiful japanese woman, 22 years old, photorealistic, professional photography, golden hour, natural smile, cute face, slim body, white summer dress, soft natural light, film grain, sharp focus, 8k uhd' },
    { label: 'Real woman cafe', text: '1girl, beautiful japanese woman, 22 years old, sitting at cafe window, casual cardigan, relaxed smile, soft window light, photorealistic, shallow depth of field, film grain' },
    { label: 'Real woman bedroom', text: '1girl, beautiful japanese woman, 22 years old, bedroom morning light, white lingerie, looking back over shoulder, soft warm sunlight, photorealistic, intimate, sharp focus' },
  ],
  illustrious: [
    { label: 'Anime portrait', text: '1girl, masterpiece, best quality, very aesthetic, beautiful detailed eyes, anime style, illustrious, school uniform, looking at viewer, gentle smile, soft lighting' },
    { label: 'Anime fantasy', text: '1girl, masterpiece, best quality, magical girl outfit, fantasy background, dynamic pose, sparkles, soft pastel colors, anime style' },
  ],
  wan_i2v: [
    { label: 'Subtle motion', text: 'gentle hair movement in wind, slight body sway, soft smile, smooth motion, high quality animation' },
    { label: 'Look at camera', text: 'turning slowly to face camera, soft expression, smooth rotation, hair shifts gently' },
    { label: 'Hair wind', text: 'hair flowing in wind, fabric fluttering, looking out at horizon, cinematic, smooth motion' },
    { label: 'Smile blink', text: 'gentle smile, blinking softly, slight head tilt, very subtle motion' },
  ],
}

function GenerateTab() {
  const [model, setModel] = useState<ModelKind>('z_image')
  const [prompt, setPrompt] = useState('')
  const [width, setWidth] = useState(1080)
  const [height, setHeight] = useState(1920)
  const [submitting, setSubmitting] = useState(false)
  const [job, setJob] = useState<GenJob | null>(null)
  const [polling, setPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loras, setLoras] = useState<Array<{ id: string; name: string; strength: number }>>([])
  const [loraOptions, setLoraOptions] = useState<string[]>([])
  // Wan I2V specific
  const [imageUrl, setImageUrl] = useState('')
  const [length, setLength] = useState(33)
  const [fps, setFps] = useState(16)
  // Advanced controls (matches PC version's KSampler + negative prompt)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [steps, setSteps] = useState(8)
  const [cfg, setCfg] = useState(1.0)
  const [samplerName, setSamplerName] = useState('euler')
  const [scheduler, setScheduler] = useState('simple')
  const [seedMode, setSeedMode] = useState<'random' | 'fixed'>('random')
  const [seedValue, setSeedValue] = useState(42)
  const [negativePrompt, setNegativePrompt] = useState('')
  // Loop mode (matches PC version's Loop button — continuous generation)
  const [looping, setLooping] = useState(false)
  const [loopCount, setLoopCount] = useState(0)
  const loopActiveRef = useRef(false)
  // Loop budget cap (USD)
  const [loopBudget, setLoopBudget] = useState(2.0)
  const [loopSpent, setLoopSpent] = useState(0.0)
  // Presets
  const [presets, setPresets] = useState<Preset[]>([])
  const [selectedPresetId, setSelectedPresetId] = useState<string>('')
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveKind, setSaveKind] = useState<'template' | 'character'>('template')
  const [saveCharName, setSaveCharName] = useState('')
  // Per-submit cost estimate
  const [costEstimate, setCostEstimate] = useState<number | null>(null)
  // A/B compare mode
  const [abBatchId, setAbBatchId] = useState<string | null>(null)
  const [abJobs, setAbJobs] = useState<Array<{
    variation_index: number
    remote_job_id: string
    status: string
    prompt?: string
    output_url?: string
    last_error?: string
  }>>([])
  const [abPolling, setAbPolling] = useState(false)
  const [abSubmitting, setAbSubmitting] = useState(false)

  // Fetch LoRA options from inventory once
  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/m/inventory')
        const data: InventoryResp = await res.json()
        const loras = (data?.inventory?.loras || []).map((f) => f.filename)
        setLoraOptions(loras.sort())
      } catch (e) {
        console.error('inventory fetch failed', e)
      }
    })()
  }, [])

  // Load presets once
  const loadPresets = useCallback(async () => {
    try {
      const res = await fetch('/api/m/presets')
      const data = await res.json()
      if (data?.ok) setPresets(data.presets || [])
    } catch (e) {
      console.error('preset fetch failed', e)
    }
  }, [])
  useEffect(() => { void loadPresets() }, [loadPresets])

  // A/B batch polling
  useEffect(() => {
    if (!abBatchId) {
      setAbPolling(false)
      return
    }
    // Check if all jobs are terminal
    const allDone = abJobs.length > 0 && abJobs.every((j) =>
      ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(j.status)
    )
    if (allDone) {
      setAbPolling(false)
      return
    }
    setAbPolling(true)
    const t = setInterval(async () => {
      try {
        const res = await fetch(`/api/m/batch/${abBatchId}`)
        const data = await res.json()
        if (data?.ok && data.batch?.jobs) {
          setAbJobs(data.batch.jobs)
        }
      } catch (e) {
        console.error('AB poll failed', e)
      }
    }, 4000)
    return () => clearInterval(t)
  }, [abBatchId, abJobs])

  // Live cost estimate (debounced)
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const params = new URLSearchParams({
          model,
          width: String(width),
          height: String(height),
          steps: String(steps),
          length: String(length),
          fps: String(fps),
        })
        const res = await fetch(`/api/m/cost/estimate?${params}`)
        const data = await res.json()
        if (data?.ok) setCostEstimate(data.est_cost_usd)
      } catch {}
    }, 300)
    return () => clearTimeout(t)
  }, [model, width, height, steps, length, fps])

  // Apply default dimensions + KSampler presets when model changes
  const onModelChange = (next: string) => {
    const m = (next as ModelKind)
    setModel(m)
    if (m === 'z_image') {
      setWidth(1080)
      setHeight(1920)
      setSteps(8)
      setCfg(1.0)
      setSamplerName('euler')
      setScheduler('simple')
    } else if (m === 'illustrious') {
      setWidth(1024)
      setHeight(1536)
      setSteps(30)
      setCfg(7.0)
      setSamplerName('dpmpp_2m_sde')
      setScheduler('karras')
    } else if (m === 'wan_i2v') {
      setWidth(480)
      setHeight(832)
      setSteps(20)
      setCfg(3.5)
      setSamplerName('euler')
      setScheduler('simple')
    }
  }

  // Polling
  useEffect(() => {
    if (!job) {
      setPolling(false)
      return
    }
    // Terminal states — stop polling; loop handler will trigger next iteration
    if (job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELLED') {
      setPolling(false)
      // If in loop mode and this completed, check budget then fire next
      if (loopActiveRef.current && job.status === 'COMPLETED') {
        const cost = costEstimate || 0.04
        const newSpent = loopSpent + cost
        setLoopSpent(newSpent)

        if (loopBudget > 0 && newSpent >= loopBudget) {
          // Budget exceeded — stop loop
          loopActiveRef.current = false
          setLooping(false)
          setError(`Loop stopped: budget $${loopBudget.toFixed(2)} reached ($${newSpent.toFixed(3)} spent)`)
          return
        }

        const timer = setTimeout(() => {
          if (loopActiveRef.current) {
            setLoopCount((c) => c + 1)
            void submitInternal()
          }
        }, 2000)  // 2s pause between loop iterations
        return () => clearTimeout(timer)
      }
      return
    }
    setPolling(true)
    const t = setInterval(async () => {
      try {
        const res = await fetch(`/api/m/status/${job.remote_job_id}`)
        const data = await res.json()
        if (data?.ok) {
          setJob({
            remote_job_id: job.remote_job_id,
            status: String(data.status || 'UNKNOWN').toUpperCase(),
            output: data.output,
            error: data.output?.error || data.error,
          })
        }
      } catch (e) {
        console.error('poll failed', e)
      }
    }, 5000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job])

  const submitInternal = async () => {
    if (!prompt.trim()) {
      setError('Prompt is required')
      loopActiveRef.current = false
      setLooping(false)
      return
    }
    if (model === 'wan_i2v' && !imageUrl.trim()) {
      setError('Image URL is required for Wan I2V')
      loopActiveRef.current = false
      setLooping(false)
      return
    }
    setError(null)
    setSubmitting(true)
    setJob(null)
    try {
      const body: Record<string, unknown> = {
        model, prompt, width, height,
        steps, cfg,
        sampler_name: samplerName,
        scheduler,
        negative: negativePrompt,
      }
      if (seedMode === 'fixed') {
        body.seed = seedValue
      }
      if (loras.length > 0 && model !== 'wan_i2v') {
        body.loras = loras
          .filter((l) => l.name && l.name !== '__none__')
          .map((l) => ({ name: l.name, strength: l.strength }))
      }
      if (model === 'wan_i2v') {
        body.image_url = imageUrl.trim()
        body.length = length
        body.fps = fps
      }
      const res = await fetch('/api/m/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!data?.ok) {
        setError(data?.error || 'submit failed')
        return
      }
      setJob({ remote_job_id: data.remote_job_id, status: 'IN_QUEUE' })
    } catch (e) {
      setError(String(e))
      loopActiveRef.current = false
      setLooping(false)
    } finally {
      setSubmitting(false)
    }
  }

  const submit = () => {
    loopActiveRef.current = false
    setLooping(false)
    setLoopCount(0)
    setLoopSpent(0)
    void submitInternal()
  }

  const startLoop = () => {
    loopActiveRef.current = true
    setLooping(true)
    setLoopCount(1)
    setLoopSpent(0)
    void submitInternal()
  }

  const stopLoop = () => {
    loopActiveRef.current = false
    setLooping(false)
  }

  // Preset handlers
  const applyPreset = (p: Preset) => {
    setModel(p.model)
    setPrompt(p.prompt)
    setNegativePrompt(p.negative || '')
    setWidth(p.width)
    setHeight(p.height)
    setSteps(p.steps)
    setCfg(p.cfg)
    setSamplerName(p.sampler_name)
    setScheduler(p.scheduler)
    setSeedMode(p.seed_mode)
    if (p.seed_value != null) setSeedValue(p.seed_value)
    setLoras(
      (p.loras || []).map((l) => ({
        id: crypto.randomUUID?.() || String(Date.now() + Math.random()),
        name: l.name,
        strength: l.strength,
      }))
    )
    setSelectedPresetId(p.id || '')
  }

  const onPresetSelect = (id: string) => {
    setSelectedPresetId(id)
    if (!id || id === '__new__') return
    const p = presets.find((x) => x.id === id)
    if (p) applyPreset(p)
  }

  const savePreset = async () => {
    if (!saveName.trim()) {
      setError('Preset name required')
      return
    }
    const body: Preset = {
      name: saveName.trim(),
      kind: saveKind,
      model,
      prompt,
      negative: negativePrompt,
      loras: loras
        .filter((l) => l.name && l.name !== '__none__')
        .map((l) => ({ name: l.name, strength: l.strength })),
      width, height, steps, cfg,
      sampler_name: samplerName,
      scheduler,
      seed_mode: saveKind === 'character' ? 'fixed' : seedMode,
      seed_value: seedValue,
    }
    if (saveKind === 'character' && saveCharName.trim()) {
      body.character_name = saveCharName.trim()
    }
    try {
      const res = await fetch('/api/m/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!data?.ok) {
        setError(data?.error || 'save failed')
        return
      }
      setSaveOpen(false)
      setSaveName('')
      setSaveCharName('')
      setSelectedPresetId(data.preset.id)
      await loadPresets()
    } catch (e) {
      setError(String(e))
    }
  }

  // A/B compare: submit 2 variations (same prompt/loras, different seeds)
  const submitAB = async (count: 2 | 4 = 2) => {
    if (!prompt.trim()) {
      setError('Prompt is required')
      return
    }
    if (model === 'wan_i2v') {
      setError('A/B not supported for Wan I2V (too expensive). Use image gen models.')
      return
    }
    setError(null)
    setAbSubmitting(true)
    setAbJobs([])
    setAbBatchId(null)
    try {
      const base: Record<string, unknown> = {
        model, prompt, width, height, steps, cfg,
        sampler_name: samplerName,
        scheduler,
        negative: negativePrompt,
      }
      if (loras.length > 0) {
        base.loras = loras
          .filter((l) => l.name && l.name !== '__none__')
          .map((l) => ({ name: l.name, strength: l.strength }))
      }
      const variations = Array.from({ length: count }, () => ({}))  // empty = each gets random seed
      const res = await fetch('/api/m/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `AB ${count}x ${new Date().toLocaleTimeString()}`,
          base, variations,
        }),
      })
      const data = await res.json()
      if (!data?.ok) {
        setError(data?.error || 'A/B submit failed')
        return
      }
      setAbBatchId(data.batch_id)
      setAbJobs(data.batch?.jobs || [])
    } catch (e) {
      setError(String(e))
    } finally {
      setAbSubmitting(false)
    }
  }

  const pickAB = (jobIndex: number) => {
    // When user picks A or B, the frontend can't know exact seed because backend
    // generates it. We just record which one was picked via preset save.
    // Best UX: user taps "Use this" on preferred, we save as preset with kind=character
    // For now, clear AB and user can re-generate single with current settings
    const job = abJobs[jobIndex]
    if (!job) return
    setAbJobs([])
    setAbBatchId(null)
    // Could set job result as main display
    if (job.output_url) {
      setJob({
        remote_job_id: job.remote_job_id,
        status: 'COMPLETED',
        output: { url: job.output_url },
      })
    }
  }

  const clearAB = () => {
    setAbJobs([])
    setAbBatchId(null)
  }

  const deleteSelectedPreset = async () => {
    if (!selectedPresetId || selectedPresetId === '__new__') return
    const p = presets.find((x) => x.id === selectedPresetId)
    if (!p) return
    if (!confirm(`Delete preset "${p.name}"?`)) return
    try {
      await fetch(`/api/m/presets/${selectedPresetId}`, { method: 'DELETE' })
      setSelectedPresetId('')
      await loadPresets()
    } catch (e) {
      console.error('delete failed', e)
    }
  }

  // Output extraction: image URL or video URL
  const outputUrl = job?.output?.url ? String(job.output.url) : null
  const outputVideos = (job?.output?.videos as Array<{ url?: string }> | undefined) || []
  const videoUrl = outputVideos.length > 0 ? outputVideos[0].url : null
  const isVideoOutput = model === 'wan_i2v' || !!videoUrl
  const finalOutputUrl = videoUrl || outputUrl

  const selectedPreset = presets.find((p) => p.id === selectedPresetId)

  return (
    <div className="px-3 py-3 space-y-4">
      {/* Preset picker (Template Library + Character Anchor) */}
      <div className="space-y-1.5 rounded-lg border border-purple-500/30 bg-purple-500/5 p-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-purple-300 flex items-center gap-1">
            <BookOpen className="w-3 h-3" /> Preset Library
          </label>
          <div className="flex items-center gap-1">
            {selectedPresetId && selectedPresetId !== '__new__' && (
              <button
                onClick={deleteSelectedPreset}
                className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/30 text-red-300 hover:bg-red-500/10"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
            <button
              onClick={() => setSaveOpen(true)}
              className="text-[10px] px-2 py-0.5 rounded border border-purple-500/40 bg-purple-500/20 text-purple-200 hover:bg-purple-500/30 flex items-center gap-1"
            >
              <Save className="w-3 h-3" /> Save current
            </button>
          </div>
        </div>
        <Select value={selectedPresetId || '__none__'} onValueChange={(v) => onPresetSelect(v === '__none__' ? '' : v)}>
          <SelectTrigger className="w-full h-9 text-xs">
            <SelectValue placeholder="(load a preset...)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__" className="text-xs text-muted-foreground">(none)</SelectItem>
            {/* Characters first */}
            {presets.filter((p) => p.kind === 'character').length > 0 && (
              <>
                {presets
                  .filter((p) => p.kind === 'character')
                  .map((p) => (
                    <SelectItem key={p.id} value={p.id || ''} className="text-xs">
                      <span className="inline-flex items-center gap-1">
                        <User className="w-3 h-3 text-orange-400" />
                        {p.character_name || p.name}
                      </span>
                    </SelectItem>
                  ))}
              </>
            )}
            {presets
              .filter((p) => p.kind === 'template')
              .map((p) => (
                <SelectItem key={p.id} value={p.id || ''} className="text-xs">
                  {p.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
        {selectedPreset && (
          <p className="text-[9px] text-muted-foreground">
            {selectedPreset.kind === 'character' ? '🎭 Character' : '📋 Template'}
            {' · '}{selectedPreset.model}
            {' · '}{selectedPreset.width}×{selectedPreset.height}
            {selectedPreset.seed_mode === 'fixed' && ` · seed ${selectedPreset.seed_value}`}
          </p>
        )}
      </div>

      {/* Save Preset dialog */}
      {saveOpen && (
        <div className="rounded-lg border border-purple-500/40 bg-purple-500/10 p-3 space-y-2">
          <div className="text-xs font-medium text-purple-200">Save current settings as...</div>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setSaveKind('template')}
              className={`text-[10px] px-2 py-1.5 rounded border ${saveKind === 'template' ? 'border-purple-400 bg-purple-500/30 text-purple-100' : 'border-border/40 text-muted-foreground'}`}
            >
              📋 Template (random seed OK)
            </button>
            <button
              onClick={() => setSaveKind('character')}
              className={`text-[10px] px-2 py-1.5 rounded border ${saveKind === 'character' ? 'border-orange-400 bg-orange-500/30 text-orange-100' : 'border-border/40 text-muted-foreground'}`}
            >
              🎭 Character (fixed seed)
            </button>
          </div>
          <Input
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            placeholder="Preset name (e.g. 'Real woman cafe')"
            className="h-8 text-xs"
          />
          {saveKind === 'character' && (
            <>
              <Input
                value={saveCharName}
                onChange={(e) => setSaveCharName(e.target.value)}
                placeholder="Character name (e.g. 'Rin')"
                className="h-8 text-xs"
              />
              <p className="text-[9px] text-orange-300">
                Seed will be locked to {seedValue} — this character&apos;s face is reproducible.
              </p>
            </>
          )}
          <div className="flex gap-2">
            <Button onClick={savePreset} size="sm" className="flex-1 h-8 text-xs bg-purple-500 hover:bg-purple-600 text-white">
              Save
            </Button>
            <Button onClick={() => { setSaveOpen(false); setSaveName(''); setSaveCharName('') }} variant="outline" size="sm" className="h-8 text-xs">
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Model picker */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">Model</label>
        <Select value={model} onValueChange={onModelChange}>
          <SelectTrigger className="w-full h-10">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="z_image">Z-Image Turbo (Real, fast)</SelectItem>
            <SelectItem value="illustrious">Illustrious XL (Anime)</SelectItem>
            <SelectItem value="wan_i2v">Wan 2.2 I2V (Image → Video, 5-10 min)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Image URL input (only for Wan I2V) */}
      {model === 'wan_i2v' && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            Input Image URL <span className="text-orange-400">*</span>
          </label>
          <Input
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
            placeholder="https://... (R2 or any public image URL)"
            className="h-9 text-xs font-mono"
          />
          <p className="text-[10px] text-muted-foreground">
            Tip: Generate an image first (Z-Image / Illustrious), then paste its URL here
          </p>
        </div>
      )}

      {/* Prompt presets */}
      <div className="flex flex-wrap gap-1.5">
        {PROMPT_PRESETS[model].map((p) => (
          <button
            key={p.label}
            onClick={() => setPrompt(p.text)}
            className="text-[10px] px-2 py-1 rounded-md border border-border/50 bg-card hover:border-orange-400/50 transition-colors"
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Prompt textarea */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">Prompt</label>
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe what you want to generate..."
          className="min-h-[120px] text-sm"
        />
      </div>

      {/* LoRA selector — multi-LoRA (image gen only; Wan I2V skips for now) */}
      {model !== 'wan_i2v' && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground">
              LoRAs (optional, {loras.length} added)
            </label>
            <button
              onClick={() =>
                setLoras((prev) => [
                  ...prev,
                  {
                    id: crypto.randomUUID?.() || String(Date.now() + Math.random()),
                    name: '__none__',
                    strength: 0.8,
                  },
                ])
              }
              disabled={loras.length >= 8}
              className="text-[10px] px-2 py-1 rounded-md border border-orange-500/30 bg-orange-500/10 text-orange-400 hover:bg-orange-500/20 transition-colors disabled:opacity-40"
            >
              + Add LoRA
            </button>
          </div>

          {loraOptions.length === 0 && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-400">
              LoRA list not loaded yet (inventory fetch in progress or failed).
              Names can still be typed manually if you know them, or retry via Models tab.
            </div>
          )}

          {loras.length === 0 && (
            <p className="text-[10px] text-muted-foreground italic">
              No LoRAs selected. Tap &quot;+ Add LoRA&quot; to stack quality boosters, characters, or concepts.
            </p>
          )}

          {loras.map((lora, idx) => (
            <div
              key={lora.id}
              className="space-y-1.5 rounded-md border border-border/40 bg-card/30 p-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-muted-foreground w-5 shrink-0">
                  {idx + 1}.
                </span>
                <Select
                  value={lora.name}
                  onValueChange={(v) =>
                    setLoras((prev) =>
                      prev.map((l) => (l.id === lora.id ? { ...l, name: v } : l))
                    )
                  }
                >
                  <SelectTrigger className="flex-1 min-w-0 h-8 text-xs">
                    <SelectValue placeholder="(select LoRA)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">(none)</SelectItem>
                    {loraOptions.map((name) => (
                      <SelectItem key={name} value={name} className="text-xs">
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <button
                  onClick={() =>
                    setLoras((prev) => prev.filter((l) => l.id !== lora.id))
                  }
                  className="shrink-0 h-7 w-7 rounded-md flex items-center justify-center hover:bg-red-500/20 text-muted-foreground hover:text-red-400 transition-colors"
                  aria-label="Remove LoRA"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              {lora.name !== '__none__' && (
                <div className="flex items-center gap-2">
                  <Slider
                    value={[lora.strength]}
                    onValueChange={([v]) =>
                      setLoras((prev) =>
                        prev.map((l) => (l.id === lora.id ? { ...l, strength: v } : l))
                      )
                    }
                    min={0}
                    max={2}
                    step={0.05}
                    className="flex-1"
                  />
                  <span className="text-[10px] font-mono text-muted-foreground w-10 text-right">
                    {lora.strength.toFixed(2)}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Dimensions */}
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <label className="text-[10px] font-medium text-muted-foreground">Width</label>
          <Input
            type="number"
            value={width}
            onChange={(e) => setWidth(parseInt(e.target.value) || 0)}
            className="h-8 text-xs"
            min={256}
            max={2048}
            step={64}
          />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-medium text-muted-foreground">Height</label>
          <Input
            type="number"
            value={height}
            onChange={(e) => setHeight(parseInt(e.target.value) || 0)}
            className="h-8 text-xs"
            min={256}
            max={2048}
            step={64}
          />
        </div>
      </div>

      {/* Wan I2V specific: length + fps */}
      {model === 'wan_i2v' && (
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="text-[10px] font-medium text-muted-foreground">Frames</label>
            <Input
              type="number"
              value={length}
              onChange={(e) => setLength(parseInt(e.target.value) || 33)}
              className="h-8 text-xs"
              min={9}
              max={161}
              step={4}
            />
            <p className="text-[9px] text-muted-foreground">33 frames @ 16fps ≈ 2 sec</p>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-medium text-muted-foreground">FPS</label>
            <Input
              type="number"
              value={fps}
              onChange={(e) => setFps(parseInt(e.target.value) || 16)}
              className="h-8 text-xs"
              min={8}
              max={32}
              step={2}
            />
          </div>
        </div>
      )}

      {/* Advanced controls (collapsible — mirrors PC's KSampler + negative prompt) */}
      <div className="rounded-lg border border-border/40 bg-card/20">
        <button
          onClick={() => setAdvancedOpen((v) => !v)}
          className="w-full flex items-center justify-between p-3 text-xs font-medium hover:bg-card/40 transition-colors"
        >
          <span>Advanced (KSampler / Negative / Seed)</span>
          <span className={`transition-transform ${advancedOpen ? 'rotate-90' : ''}`}>›</span>
        </button>

        {advancedOpen && (
          <div className="border-t border-border/40 p-3 space-y-3">
            {/* Steps + CFG */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[10px] font-medium text-muted-foreground">Steps</label>
                <Input
                  type="number"
                  value={steps}
                  onChange={(e) => setSteps(parseInt(e.target.value) || 0)}
                  className="h-8 text-xs"
                  min={1}
                  max={100}
                />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-medium text-muted-foreground">CFG</label>
                <Input
                  type="number"
                  value={cfg}
                  onChange={(e) => setCfg(parseFloat(e.target.value) || 0)}
                  className="h-8 text-xs"
                  min={0}
                  max={30}
                  step={0.1}
                />
              </div>
            </div>

            {/* Sampler + Scheduler */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[10px] font-medium text-muted-foreground">Sampler</label>
                <Select value={samplerName} onValueChange={setSamplerName}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {['euler', 'euler_ancestral', 'heun', 'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_2m_sde_gpu', 'dpmpp_3m_sde', 'dpmpp_sde', 'ddim', 'uni_pc', 'lcm', 'res_multistep'].map((s) => (
                      <SelectItem key={s} value={s} className="text-xs">
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-medium text-muted-foreground">Scheduler</label>
                <Select value={scheduler} onValueChange={setScheduler}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {['simple', 'karras', 'normal', 'exponential', 'sgm_uniform', 'beta', 'ddim_uniform', 'linear_quadratic', 'kl_optimal'].map((s) => (
                      <SelectItem key={s} value={s} className="text-xs">
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Seed mode */}
            <div className="space-y-1">
              <label className="text-[10px] font-medium text-muted-foreground">Seed</label>
              <div className="grid grid-cols-2 gap-2">
                <Select value={seedMode} onValueChange={(v) => setSeedMode(v as 'random' | 'fixed')}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="random" className="text-xs">Random</SelectItem>
                    <SelectItem value="fixed" className="text-xs">Fixed</SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  type="number"
                  value={seedValue}
                  onChange={(e) => setSeedValue(parseInt(e.target.value) || 0)}
                  className="h-8 text-xs font-mono"
                  disabled={seedMode === 'random'}
                  min={0}
                  max={2147483647}
                />
              </div>
              {seedMode === 'random' && (
                <p className="text-[9px] text-muted-foreground italic">
                  New seed each generation (can&apos;t reproduce exactly)
                </p>
              )}
            </div>

            {/* Negative prompt */}
            <div className="space-y-1">
              <label className="text-[10px] font-medium text-muted-foreground">
                Negative Prompt (overrides default)
              </label>
              <Textarea
                value={negativePrompt}
                onChange={(e) => setNegativePrompt(e.target.value)}
                placeholder={model === 'illustrious'
                  ? '(leave blank to use default: lowres, bad anatomy, ...)'
                  : model === 'z_image'
                    ? '(Z-Image works best with EMPTY negative — leave blank)'
                    : '(leave blank to use default)'
                }
                className="min-h-[60px] text-xs"
              />
            </div>
          </div>
        )}
      </div>

      {/* Submit buttons — Generate (single) / Loop (continuous) / Stop (when looping) */}
      <div className="space-y-2">
        {/* Cost estimate pre-submit */}
        {costEstimate !== null && !looping && (
          <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
            <span>Est. cost per generation:</span>
            <span className="font-mono text-emerald-400">
              ${costEstimate.toFixed(4)} USD
            </span>
          </div>
        )}

        {!looping ? (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Button
                onClick={submit}
                disabled={submitting || !prompt.trim()}
                className="col-span-2 h-12 text-sm font-semibold bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white"
              >
                {submitting ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Submitting...</>
                ) : (
                  <><Sparkles className="w-4 h-4 mr-2" /> Generate</>
                )}
              </Button>
              <Button
                onClick={startLoop}
                disabled={submitting || !prompt.trim() || seedMode === 'fixed'}
                variant="outline"
                className="h-12 text-xs font-semibold border-purple-500/40 bg-purple-500/10 text-purple-300 hover:bg-purple-500/20"
                title={seedMode === 'fixed' ? 'Loop requires random seed' : 'Continuous generation with new seed each iteration'}
              >
                <Repeat className="w-4 h-4 mr-1" /> Loop
              </Button>
            </div>
            {/* Budget cap input (shown near Loop button) */}
            <div className="flex items-center gap-2 px-1">
              <label className="text-[10px] text-muted-foreground flex items-center gap-1 shrink-0">
                <DollarSign className="w-3 h-3" /> Loop budget:
              </label>
              <Input
                type="number"
                value={loopBudget}
                onChange={(e) => setLoopBudget(parseFloat(e.target.value) || 0)}
                className="h-7 text-[10px] font-mono flex-1"
                min={0}
                max={100}
                step={0.5}
              />
              <span className="text-[10px] text-muted-foreground">USD (0 = no cap)</span>
            </div>
          </>
        ) : (
          <>
            <Button
              onClick={stopLoop}
              className="w-full h-12 text-sm font-semibold bg-gradient-to-r from-red-500 to-purple-500 hover:from-red-600 hover:to-purple-600 text-white animate-pulse"
            >
              <Square className="w-4 h-4 mr-2 fill-white" />
              Stop Loop (iter {loopCount} · ${loopSpent.toFixed(3)})
            </Button>
            {loopBudget > 0 && (
              <div className="h-1.5 rounded-full bg-card overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-amber-500 transition-all"
                  style={{ width: `${Math.min(100, (loopSpent / loopBudget) * 100)}%` }}
                />
              </div>
            )}
            <p className="text-[10px] text-purple-300 text-center">
              🔁 Loop active · {loopSpent.toFixed(3)} / {loopBudget > 0 ? loopBudget.toFixed(2) : '∞'} USD
            </p>
          </>
        )}

        {seedMode === 'fixed' && !looping && (
          <p className="text-[9px] text-muted-foreground italic text-center">
            Loop disabled: seed mode is &quot;Fixed&quot; — switch to Random in Advanced to enable
          </p>
        )}

        {/* A/B compare buttons */}
        {!looping && model !== 'wan_i2v' && (
          <div className="grid grid-cols-2 gap-2 pt-1">
            <Button
              onClick={() => submitAB(2)}
              disabled={abSubmitting || !prompt.trim() || abPolling}
              variant="outline"
              className="h-10 text-xs border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
              title="Submit 2 generations with different seeds to compare"
            >
              {abSubmitting ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <GitCompareArrows className="w-3.5 h-3.5 mr-1" />}
              A/B (2 images)
            </Button>
            <Button
              onClick={() => submitAB(4)}
              disabled={abSubmitting || !prompt.trim() || abPolling}
              variant="outline"
              className="h-10 text-xs border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
              title="Submit 4 generations with different seeds (2x2 grid)"
            >
              {abSubmitting ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Layers className="w-3.5 h-3.5 mr-1" />}
              2×2 Grid (4)
            </Button>
          </div>
        )}
      </div>

      {/* A/B compare result panel */}
      {abJobs.length > 0 && (
        <div className="rounded-lg border border-cyan-500/40 bg-cyan-500/5 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GitCompareArrows className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-medium text-cyan-300">
                Compare ({abJobs.length} variants)
              </span>
              {abPolling && <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />}
            </div>
            <button
              onClick={clearAB}
              className="text-[10px] text-muted-foreground hover:text-red-400"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
          <div className={`grid gap-2 ${abJobs.length <= 2 ? 'grid-cols-2' : 'grid-cols-2'}`}>
            {abJobs.map((j, i) => {
              const letter = String.fromCharCode(65 + i)  // A, B, C, D
              const done = j.status === 'COMPLETED' && j.output_url
              const failed = ['FAILED', 'CANCELLED', 'TIMED_OUT'].includes(j.status)
              return (
                <div
                  key={j.remote_job_id}
                  className="relative rounded-lg overflow-hidden border border-border/40 bg-card aspect-[9/16]"
                >
                  <div className="absolute top-1 left-1 z-10 h-5 w-5 rounded bg-cyan-500/80 flex items-center justify-center text-[10px] font-bold text-white">
                    {letter}
                  </div>
                  {done ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={j.output_url} alt={`Variant ${letter}`} className="w-full h-full object-cover" loading="lazy" />
                      <button
                        onClick={() => pickAB(i)}
                        className="absolute bottom-0 inset-x-0 px-2 py-1.5 bg-gradient-to-t from-black/90 to-transparent text-white text-[10px] font-medium"
                      >
                        ⭐ Use this
                      </button>
                    </>
                  ) : failed ? (
                    <div className="flex flex-col items-center justify-center h-full p-2 text-center">
                      <AlertCircle className="w-5 h-5 text-red-400 mb-1" />
                      <span className="text-[9px] text-red-300">{j.status}</span>
                      {j.last_error && (
                        <span className="text-[8px] text-muted-foreground truncate">{j.last_error}</span>
                      )}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full">
                      <Loader2 className="w-5 h-5 animate-spin text-cyan-400 mb-1" />
                      <span className="text-[9px] text-cyan-300">{j.status || 'submitting'}</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <p className="text-[9px] text-muted-foreground text-center">
            Same prompt + LoRAs, different random seeds. Tap &quot;Use this&quot; to keep the best as main result.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Job status */}
      {job && (
        <div className="rounded-lg border border-border/40 bg-card/50 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium">Status</span>
            <Badge
              variant="outline"
              className={`text-[10px] ${
                job.status === 'COMPLETED' ? 'border-emerald-500/40 text-emerald-400' :
                job.status === 'FAILED' ? 'border-red-500/40 text-red-400' :
                'border-amber-500/40 text-amber-400'
              }`}
            >
              {job.status}
              {polling && <Loader2 className="w-3 h-3 ml-1 animate-spin inline" />}
            </Badge>
          </div>
          <div className="text-[10px] font-mono text-muted-foreground truncate">
            {job.remote_job_id}
          </div>

          {finalOutputUrl && (
            <div className="space-y-2 pt-2">
              <div className="flex items-center gap-1.5 text-xs text-emerald-400">
                <CheckCircle2 className="w-3 h-3" />
                {isVideoOutput ? 'Video ready' : 'Image ready'}
              </div>
              {isVideoOutput ? (
                <video
                  src={finalOutputUrl}
                  controls
                  loop
                  className="w-full rounded-lg border border-border/40"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={finalOutputUrl}
                  alt="Generated"
                  className="w-full rounded-lg border border-border/40"
                  loading="lazy"
                />
              )}
              <div className="flex items-center gap-2">
                <a
                  href={finalOutputUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-orange-400 hover:underline flex items-center gap-1"
                >
                  Open original <ExternalLink className="w-3 h-3" />
                </a>
                {!isVideoOutput && finalOutputUrl && (
                  <button
                    onClick={() => {
                      setModel('wan_i2v')
                      setImageUrl(finalOutputUrl)
                      setWidth(480)
                      setHeight(832)
                    }}
                    className="text-[10px] text-pink-400 hover:underline flex items-center gap-1 ml-auto"
                  >
                    Animate this → I2V
                  </button>
                )}
              </div>
            </div>
          )}

          {job.error && (
            <div className="text-[10px] text-red-400 mt-1">{job.error}</div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// Models Tab — inventory of RunPod Network Volume
// ============================================================

const MODEL_TYPE_LABELS: Record<string, string> = {
  checkpoints: 'Checkpoints',
  diffusion_models: 'Diffusion Models',
  text_encoders: 'Text Encoders',
  vae: 'VAE',
  clip_vision: 'Clip Vision',
  loras: 'LoRAs',
  upscale_models: 'Upscale Models',
}

function ModelsTab() {
  const [data, setData] = useState<InventoryResp | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/m/inventory')
      const json: InventoryResp = await res.json()
      if (json?.ok) {
        setData(json)
      } else {
        setError('Failed to load inventory')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="px-3 py-3">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          Network Volume Inventory
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={load}
          disabled={loading}
          className="h-7 px-2 text-xs"
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 mb-3">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="space-y-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : data ? (
        <>
          {/* Grand total */}
          <div className="rounded-lg border border-orange-500/30 bg-gradient-to-br from-orange-500/5 to-pink-500/5 p-3 mb-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Total</div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tabular-nums">{data.grand_total?.files || 0}</span>
              <span className="text-xs text-muted-foreground">files</span>
              <span className="text-xs text-muted-foreground ml-auto font-mono">
                {((data.grand_total?.size_mb || 0) / 1024).toFixed(1)} GB / 200 GB
              </span>
            </div>
          </div>

          {/* Per-category */}
          <div className="space-y-1.5">
            {Object.entries(MODEL_TYPE_LABELS).map(([mt, label]) => {
              const items = data.inventory?.[mt] || []
              const total = data.totals?.[mt]
              const isExpanded = expanded === mt
              return (
                <div key={mt} className="rounded-lg border border-border/40 bg-card/30 overflow-hidden">
                  <button
                    onClick={() => setExpanded(isExpanded ? null : mt)}
                    className="w-full flex items-center justify-between p-3 hover:bg-card/50 transition-colors"
                  >
                    <div className="flex items-center gap-2 text-left">
                      <span className="text-xs font-medium">{label}</span>
                      {total && (
                        <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4">
                          {total.count}
                        </Badge>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground">
                      {total ? `${(total.size_mb / 1024).toFixed(2)} GB` : '—'}
                    </span>
                  </button>
                  {isExpanded && (
                    <ul className="border-t border-border/40 max-h-64 overflow-y-auto">
                      {items.length === 0 ? (
                        <li className="px-3 py-2 text-[10px] text-muted-foreground italic">
                          (empty or fetch failed)
                        </li>
                      ) : (
                        items.map((f, i) => (
                          <li key={i} className="px-3 py-1.5 text-[10px] flex items-center justify-between gap-2 border-t border-border/20 first:border-t-0">
                            <span className="truncate font-mono text-foreground/80">{f.filename}</span>
                            <span className="text-muted-foreground/70 shrink-0">
                              {(f.size_mb || 0).toFixed(0)} MB
                            </span>
                          </li>
                        ))
                      )}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>

          {data.errors && Object.keys(data.errors).length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-[10px] text-amber-400">
              <div className="font-medium mb-1">Partial fetch errors:</div>
              {Object.entries(data.errors).map(([k, v]) => (
                <div key={k}>{k}: {v}</div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}

// ============================================================
// Helpers
// ============================================================
function isVideo(filename: string): boolean {
  const lower = filename.toLowerCase()
  return lower.endsWith('.mp4') || lower.endsWith('.webm') || lower.endsWith('.mov')
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
