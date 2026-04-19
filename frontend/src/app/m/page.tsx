'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Heart, ImageIcon, ListTodo, RefreshCw, Star, X, ExternalLink, Sparkles, Database, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
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
type TabId = 'generate' | 'gallery' | 'favorites' | 'queue' | 'models'

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
  { id: 'gallery', label: 'Gallery', Icon: ImageIcon },
  { id: 'favorites', label: 'Favs', Icon: Heart },
  { id: 'queue', label: 'Queue', Icon: ListTodo },
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
        {tab === 'gallery' && <GalleryTab />}
        {tab === 'favorites' && <FavoritesTab />}
        {tab === 'queue' && <QueueTab />}
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
  return (
    <header className="sticky top-0 z-20 border-b border-border/40 bg-background/85 backdrop-blur-md px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-orange-400 to-pink-500 flex items-center justify-center">
            <span className="text-white text-[10px] font-bold">BF</span>
          </div>
          <h1 className="text-base font-semibold tracking-tight">BlockFlow</h1>
          <Badge variant="outline" className="text-[9px] uppercase tracking-wider px-1.5 py-0 h-4">
            mobile
          </Badge>
        </div>
        <Link
          href="/generate"
          className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
        >
          Desktop UI <ExternalLink className="w-3 h-3" />
        </Link>
      </div>
    </header>
  )
}

// ============================================================
// TabBar
// ============================================================
function TabBar({ current, onChange }: { current: TabId; onChange: (id: TabId) => void }) {
  return (
    <nav className="sticky top-[57px] z-10 border-b border-border/40 bg-background/85 backdrop-blur-md">
      <div className="grid grid-cols-5">
        {TABS.map(({ id, label, Icon }) => {
          const active = current === id
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className={`relative flex flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors ${
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
  const [loraName, setLoraName] = useState<string>('__none__')
  const [loraStrength, setLoraStrength] = useState(0.8)
  const [loraOptions, setLoraOptions] = useState<string[]>([])
  // Wan I2V specific
  const [imageUrl, setImageUrl] = useState('')
  const [length, setLength] = useState(33)
  const [fps, setFps] = useState(16)

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

  // Apply default dimensions when model changes
  const onModelChange = (next: string) => {
    const m = (next as ModelKind)
    setModel(m)
    if (m === 'z_image') {
      setWidth(1080)
      setHeight(1920)
    } else if (m === 'illustrious') {
      setWidth(1024)
      setHeight(1536)
    } else if (m === 'wan_i2v') {
      setWidth(480)
      setHeight(832)
    }
  }

  // Polling
  useEffect(() => {
    if (!job || job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELLED') {
      setPolling(false)
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
  }, [job])

  const submit = async () => {
    if (!prompt.trim()) {
      setError('Prompt is required')
      return
    }
    if (model === 'wan_i2v' && !imageUrl.trim()) {
      setError('Image URL is required for Wan I2V')
      return
    }
    setError(null)
    setSubmitting(true)
    setJob(null)
    try {
      const body: Record<string, unknown> = { model, prompt, width, height }
      if (loraName !== '__none__' && model !== 'wan_i2v') {
        body.loras = [{ name: loraName, strength: loraStrength }]
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
    } finally {
      setSubmitting(false)
    }
  }

  // Output extraction: image URL or video URL
  const outputUrl = job?.output?.url ? String(job.output.url) : null
  const outputVideos = (job?.output?.videos as Array<{ url?: string }> | undefined) || []
  const videoUrl = outputVideos.length > 0 ? outputVideos[0].url : null
  const isVideoOutput = model === 'wan_i2v' || !!videoUrl
  const finalOutputUrl = videoUrl || outputUrl

  return (
    <div className="px-3 py-3 space-y-4">
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

      {/* LoRA selector (image gen only — Wan I2V skips LoRA in this MVP) */}
      {loraOptions.length > 0 && model !== 'wan_i2v' && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">LoRA (optional)</label>
          <Select value={loraName} onValueChange={setLoraName}>
            <SelectTrigger className="w-full h-9 text-xs">
              <SelectValue />
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
          {loraName !== '__none__' && (
            <div className="flex items-center gap-2">
              <Slider
                value={[loraStrength]}
                onValueChange={([v]) => setLoraStrength(v)}
                min={0}
                max={2}
                step={0.05}
                className="flex-1"
              />
              <span className="text-[10px] font-mono text-muted-foreground w-10 text-right">
                {loraStrength.toFixed(2)}
              </span>
            </div>
          )}
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

      {/* Submit */}
      <Button
        onClick={submit}
        disabled={submitting || !prompt.trim()}
        className="w-full h-12 text-sm font-semibold bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white"
      >
        {submitting ? (
          <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Submitting...</>
        ) : (
          <><Sparkles className="w-4 h-4 mr-2" /> Generate</>
        )}
      </Button>

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
