import type { RunEntry } from './types'

const BASE = '' // Same origin, proxied by Next.js rewrites

export interface FlowEntry {
  name: string
  filename: string
  updated_at: string
  size_bytes: number
}

// ---- Run History ----

export async function saveRun(run: RunEntry) {
  const res = await fetch(`${BASE}/api/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(run),
  })
  return res.json()
}

export async function fetchRuns(limit = 50, offset = 0, favorited = false) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (favorited) params.set('favorited', 'true')
  const res = await fetch(`${BASE}/api/runs?${params}`)
  return res.json()
}

export async function toggleRunFavorite(id: string) {
  const res = await fetch(`${BASE}/api/runs/${encodeURIComponent(id)}/favorite`, { method: 'PATCH' })
  return res.json()
}

export async function fetchRunById(id: string) {
  const res = await fetch(`${BASE}/api/runs/${encodeURIComponent(id)}`)
  return res.json()
}

export async function deleteRun(id: string) {
  const res = await fetch(`${BASE}/api/runs/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return res.json()
}

// ---- Flows (disk-backed, ./flows) ----

export async function fetchFlows() {
  const res = await fetch(`${BASE}/api/flows`)
  return res.json()
}

export async function fetchFlow(name: string) {
  const res = await fetch(`${BASE}/api/flows/${encodeURIComponent(name)}`)
  return res.json()
}

export async function deleteFlow(name: string) {
  const res = await fetch(`${BASE}/api/flows/${encodeURIComponent(name)}`, { method: 'DELETE' })
  return res.json()
}

export async function renameFlow(name: string, newName: string) {
  const res = await fetch(`${BASE}/api/flows/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newName }),
  })
  return res.json()
}

export async function saveFlowToDisk(name: string, flow: Record<string, unknown>) {
  const res = await fetch(`${BASE}/api/flows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, flow }),
  })
  return res.json()
}

// ---- R2 Gallery ----

export interface R2Image {
  key: string
  filename: string
  size: number
  last_modified: string
  url: string
}

export async function fetchR2Images(limit = 50, offset = 0, prefix = '') {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (prefix) params.set('prefix', prefix)
  const res = await fetch(`${BASE}/api/r2/list?${params}`)
  return res.json() as Promise<{ ok: boolean; items: R2Image[]; total: number; limit: number; offset: number; error?: string }>
}
