'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Save, RefreshCw, Trash2, Plus, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface Publication {
  id: string
  image_url: string
  title?: string
  notes?: string
  platforms?: Array<{ platform: string; status: string; url?: string; published_at?: string }>
  created_at?: string
}

const PLATFORMS = ['fanvue', 'dlsite', 'patreon', 'fanbox', 'boosty', 'twitter', 'other']
const STATUSES = ['draft', 'scheduled', 'published']

export default function PublicationsPage() {
  const [pubs, setPubs] = useState<Publication[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
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
    try {
      await fetch('/api/m/publications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_url: newImageUrl.trim(),
          title: newTitle,
          notes: newNotes,
          platforms: [{ platform: newPlatform, status: newStatus }],
        }),
      })
      setNewOpen(false)
      setNewImageUrl(''); setNewTitle(''); setNewNotes('')
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

  const filtered = pubs.filter((p) => {
    if (filter === 'all') return true
    return p.platforms?.some((pl) => pl.platform === filter)
  })

  // Stats
  const stats = {
    total: pubs.length,
    published: pubs.filter((p) => p.platforms?.some((pl) => pl.status === 'published')).length,
    draft: pubs.filter((p) => p.platforms?.some((pl) => pl.status === 'draft')).length,
    scheduled: pubs.filter((p) => p.platforms?.some((pl) => pl.status === 'scheduled')).length,
  }

  return (
    <div className="min-h-screen bg-background text-foreground pt-20 pb-12">
      <div className="max-w-6xl mx-auto px-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Save className="w-6 h-6 text-emerald-400" />
              Publications Tracker
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Track where and when each image was published across platforms.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={load} disabled={loading} variant="outline">
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button
              onClick={() => setNewOpen(true)}
              className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-4">
            <div className="text-xs text-muted-foreground uppercase tracking-wider">Total</div>
            <div className="text-2xl font-bold mt-1">{stats.total}</div>
          </div>
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
            <div className="text-xs text-emerald-400 uppercase tracking-wider">Published</div>
            <div className="text-2xl font-bold mt-1">{stats.published}</div>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="text-xs text-amber-400 uppercase tracking-wider">Scheduled</div>
            <div className="text-2xl font-bold mt-1">{stats.scheduled}</div>
          </div>
          <div className="rounded-xl border border-muted-foreground/20 bg-card/30 p-4">
            <div className="text-xs text-muted-foreground uppercase tracking-wider">Draft</div>
            <div className="text-2xl font-bold mt-1">{stats.draft}</div>
          </div>
        </div>

        {/* Add form */}
        {newOpen && (
          <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-6 space-y-3">
            <h3 className="font-semibold">New Publication</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Image URL</label>
                <Input value={newImageUrl} onChange={(e) => setNewImageUrl(e.target.value)} placeholder="From R2 gallery or direct URL" className="text-sm" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Title / caption</label>
                <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Title" className="text-sm" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Platform</label>
                <Select value={newPlatform} onValueChange={setNewPlatform}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PLATFORMS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Status</label>
                <Select value={newStatus} onValueChange={setNewStatus}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Textarea value={newNotes} onChange={(e) => setNewNotes(e.target.value)} placeholder="Notes (optional)" className="text-sm" />
            <div className="flex gap-2 justify-end">
              <Button onClick={() => setNewOpen(false)} variant="outline">Cancel</Button>
              <Button onClick={save} disabled={!newImageUrl.trim()} className="bg-emerald-500 text-white">
                Save
              </Button>
            </div>
          </div>
        )}

        {/* Platform filter */}
        <div className="flex items-center gap-2 border-b border-border/40">
          <button onClick={() => setFilter('all')} className={`px-3 py-2 text-sm font-medium border-b-2 ${filter === 'all' ? 'border-emerald-500 text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
            All
          </button>
          {PLATFORMS.map((p) => {
            const count = pubs.filter((pub) => pub.platforms?.some((pl) => pl.platform === p)).length
            if (count === 0) return null
            return (
              <button key={p} onClick={() => setFilter(p)} className={`px-3 py-2 text-sm font-medium border-b-2 ${filter === p ? 'border-emerald-500 text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                {p} <span className="text-xs">({count})</span>
              </button>
            )
          })}
        </div>

        {/* Table */}
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-border/40 bg-card/30 p-12 text-center">
            <Save className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No publications yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((p) => (
              <div key={p.id} className="rounded-lg border border-border/40 bg-card/30 p-4 flex items-start gap-4 hover:border-emerald-500/40 transition-colors">
                <div className="h-24 w-16 shrink-0 rounded overflow-hidden bg-card border border-border/20">
                  {p.image_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={p.image_url} alt="" className="w-full h-full object-cover" loading="lazy" />
                  )}
                </div>
                <div className="flex-1 min-w-0 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium truncate">{p.title || '(untitled)'}</h3>
                    {p.image_url && (
                      <a href={p.image_url} target="_blank" rel="noopener noreferrer" className="text-xs text-muted-foreground hover:text-foreground">
                        <ExternalLink className="w-3 h-3 inline" />
                      </a>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(p.platforms || []).map((pl, i) => (
                      <Badge key={i} variant="outline" className={`text-[10px] ${
                        pl.status === 'published' ? 'border-emerald-500/40 text-emerald-400' :
                        pl.status === 'scheduled' ? 'border-amber-500/40 text-amber-400' :
                        'border-muted-foreground/40'
                      }`}>
                        {pl.platform} · {pl.status}
                      </Badge>
                    ))}
                  </div>
                  {p.notes && <p className="text-xs text-muted-foreground line-clamp-2">{p.notes}</p>}
                  <p className="text-[10px] text-muted-foreground/60 font-mono">{p.created_at}</p>
                </div>
                <button onClick={() => del(p.id)} className="text-muted-foreground hover:text-red-400 shrink-0">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
