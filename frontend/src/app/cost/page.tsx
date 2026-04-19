'use client'

import { useCallback, useEffect, useState } from 'react'
import { DollarSign, RefreshCw, TrendingUp, Calendar, Hash } from 'lucide-react'
import { Button } from '@/components/ui/button'

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

export default function CostPage() {
  const [data, setData] = useState<CostSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/m/cost')
      const j = await res.json()
      if (j?.ok) setData(j)
      else setError(j?.error || 'failed to load')
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  return (
    <div className="min-h-screen bg-background text-foreground pt-20 pb-12">
      <div className="max-w-5xl mx-auto px-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <DollarSign className="w-6 h-6 text-emerald-400" />
              Cost Dashboard
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              RunPod Serverless usage tracked by /api/m/generate
            </p>
          </div>
          <Button onClick={load} disabled={loading} variant="outline">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
            {error}
          </div>
        )}

        {data && (
          <>
            {/* Top metric cards */}
            <div className="grid grid-cols-3 gap-4">
              <div className="rounded-xl border border-orange-500/30 bg-gradient-to-br from-orange-500/10 to-pink-500/5 p-6">
                <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider mb-2">
                  <Calendar className="w-3 h-3" />
                  Today
                </div>
                <div className="text-3xl font-bold font-mono">
                  ${data.today_usd.toFixed(3)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {data.today_count} generations
                </div>
              </div>
              <div className="rounded-xl border border-amber-500/30 bg-gradient-to-br from-amber-500/10 to-orange-500/5 p-6">
                <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider mb-2">
                  <TrendingUp className="w-3 h-3" />
                  Last 30 Days
                </div>
                <div className="text-3xl font-bold font-mono">
                  ${data.month_usd.toFixed(3)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {data.month_count} generations · avg ${(data.month_count > 0 ? data.month_usd / data.month_count : 0).toFixed(4)}/gen
                </div>
              </div>
              <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-teal-500/5 p-6">
                <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider mb-2">
                  <Hash className="w-3 h-3" />
                  All-Time Total
                </div>
                <div className="text-3xl font-bold font-mono">
                  ${data.total_usd.toFixed(3)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {data.total_count} generations
                </div>
              </div>
            </div>

            {/* Per-model breakdown */}
            <div className="rounded-xl border border-border/40 bg-card/30 p-6">
              <h2 className="text-lg font-semibold mb-4">Breakdown by Model</h2>
              {Object.keys(data.by_model).length === 0 ? (
                <p className="text-sm text-muted-foreground">No generations logged yet.</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(data.by_model)
                    .sort(([, a], [, b]) => b.usd - a.usd)
                    .map(([model, stats]) => {
                      const pct = data.total_usd > 0 ? (stats.usd / data.total_usd) * 100 : 0
                      return (
                        <div key={model} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="font-medium">{model}</span>
                            <span className="font-mono text-muted-foreground">
                              ${stats.usd.toFixed(3)} · {stats.count} gen · {pct.toFixed(1)}%
                            </span>
                          </div>
                          <div className="h-2 rounded-full bg-card overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-orange-500 to-pink-500"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      )
                    })}
                </div>
              )}
            </div>

            {/* Tips */}
            <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-6 text-sm">
              <h3 className="font-semibold mb-2">💡 Cost Optimization Tips</h3>
              <ul className="space-y-1.5 text-muted-foreground text-xs">
                <li>• Z-Image Turbo at 1080×1920 / 8 steps ≈ $0.04 per image</li>
                <li>• Illustrious XL at 1024×1536 / 30 steps ≈ $0.04 per image</li>
                <li>• Wan 2.2 I2V 5-second clip ≈ $0.30-0.50 — ~10× more than images</li>
                <li>• Use Loop budget cap in /m to prevent runaway costs</li>
                <li>• Consider LTX Video (roadmap) for 3-5× cheaper video generation</li>
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
