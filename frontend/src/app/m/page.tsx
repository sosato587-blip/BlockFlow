'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Heart, ImageIcon, ListTodo, RefreshCw, Star, X, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  fetchR2Images,
  fetchRuns,
  toggleRunFavorite,
  type R2Image,
} from '@/lib/api'

// ============================================================
// Types
// ============================================================
type TabId = 'gallery' | 'favorites' | 'queue'

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
  { id: 'gallery', label: 'Gallery', Icon: ImageIcon },
  { id: 'favorites', label: 'Favorites', Icon: Heart },
  { id: 'queue', label: 'Queue', Icon: ListTodo },
]

export default function MobilePage() {
  const [tab, setTab] = useState<TabId>('gallery')
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <Header />
      <TabBar current={tab} onChange={setTab} />
      <main className="flex-1 overflow-y-auto pb-24">
        {tab === 'gallery' && <GalleryTab />}
        {tab === 'favorites' && <FavoritesTab />}
        {tab === 'queue' && <QueueTab />}
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
      <div className="grid grid-cols-3">
        {TABS.map(({ id, label, Icon }) => {
          const active = current === id
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className={`relative flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors ${
                active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
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
          message="No images yet. Generate something first."
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
