'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Layers, RefreshCw, Trash2, Loader2, Plus, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface BatchJob {
  variation_index: number
  remote_job_id: string
  status: string
  prompt?: string
  output_url?: string
  est_cost_usd?: number
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
}

export default function BatchesPage() {
  const [batches, setBatches] = useState<BatchRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/m/batches')
      const data = await res.json()
      if (data?.ok) setBatches((data.batches || []).reverse())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  // Auto-refresh active batches
  useEffect(() => {
    const hasActive = batches.some((b) => b.status === 'running' || b.status === 'submitting')
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

  const del = async (id: string, name: string) => {
    if (!confirm(`Delete batch "${name}"? (Images stay in gallery)`)) return
    try {
      await fetch(`/api/m/batch/${id}`, { method: 'DELETE' })
      await load()
    } catch {}
  }

  return (
    <div className="min-h-screen bg-background text-foreground pt-20 pb-12">
      <div className="max-w-6xl mx-auto px-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Layers className="w-6 h-6 text-orange-400" />
              Batches
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Prompt-variation bulk generations. Create new batches from /m.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={load} disabled={loading} variant="outline">
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Link href="/m?tab=batch">
              <Button variant="outline">
                <Plus className="w-4 h-4 mr-2" />
                New (from /m)
                <ExternalLink className="w-3 h-3 ml-1" />
              </Button>
            </Link>
          </div>
        </div>

        {batches.length === 0 && !loading ? (
          <div className="rounded-xl border border-border/40 bg-card/30 p-12 text-center">
            <Layers className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No batches yet.</p>
            <p className="text-xs text-muted-foreground mt-2">
              Create one from the <Link href="/m?tab=batch" className="text-orange-400 hover:underline">Batch tab in /m</Link>.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {batches.map((b) => {
              const jobs = b.jobs || []
              const done = jobs.filter((j) => j.status === 'COMPLETED').length
              const failed = jobs.filter((j) => ['FAILED', 'CANCELLED', 'TIMED_OUT'].includes(j.status)).length
              const running = jobs.length - done - failed
              const isExpanded = expanded === b.id

              return (
                <div key={b.id} className="rounded-xl border border-border/40 bg-card/30 overflow-hidden">
                  <div className="flex items-center justify-between p-4">
                    <button
                      onClick={() => setExpanded(isExpanded ? null : b.id)}
                      className="flex-1 text-left space-y-1"
                    >
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium">{b.name}</h3>
                        <Badge variant="outline" className={`text-[10px] ${
                          b.status === 'completed' ? 'border-emerald-500/40 text-emerald-400' :
                          b.status === 'failed' ? 'border-red-500/40 text-red-400' :
                          'border-amber-500/40 text-amber-400'
                        }`}>
                          {b.status}
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {done}/{jobs.length} complete · {failed > 0 && `${failed} failed · `}{b.created_at}
                      </div>
                    </button>
                    <div className="flex items-center gap-2 shrink-0">
                      {running > 0 && <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />}
                      <button onClick={() => del(b.id, b.name)} className="text-muted-foreground hover:text-red-400">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="border-t border-border/40 p-4 grid grid-cols-6 gap-2">
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
                              <div className="flex items-center justify-center h-full text-[10px] text-muted-foreground">
                                {j.status}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
