'use client'

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export type BlockLayoutMode = 'auto' | 'expanded' | 'reduced'

interface BlockLayoutContextValue {
  mode: BlockLayoutMode
  setMode: (mode: BlockLayoutMode) => void
  setAutoFit: () => void
  expandAll: () => void
  reduceAll: () => void
}

const STORAGE_KEY = 'pipeline_block_layout_mode_v1'
const DEFAULT_MODE: BlockLayoutMode = 'expanded'

const BlockLayoutCtx = createContext<BlockLayoutContextValue | null>(null)

function isLayoutMode(value: unknown): value is BlockLayoutMode {
  return value === 'auto' || value === 'expanded' || value === 'reduced'
}

export function BlockLayoutProvider({ children }: { children: ReactNode }) {
  // Hydrate from sessionStorage via a lazy initializer instead of a useEffect
  // setState (which trips react-hooks/set-state-in-effect). The typeof window
  // guard keeps SSR/build-time rendering happy; on the server we fall back to
  // DEFAULT_MODE, and the client renders identically on first paint because
  // sessionStorage is only read client-side anyway.
  const [mode, setMode] = useState<BlockLayoutMode>(() => {
    if (typeof window === 'undefined') return DEFAULT_MODE
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      return isLayoutMode(raw) ? raw : DEFAULT_MODE
    } catch {
      return DEFAULT_MODE
    }
  })

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, mode)
    } catch {
      // ignore storage access failures
    }
  }, [mode])

  const value = useMemo<BlockLayoutContextValue>(() => ({
    mode,
    setMode,
    setAutoFit: () => setMode('auto'),
    expandAll: () => setMode('expanded'),
    reduceAll: () => setMode('reduced'),
  }), [mode])

  return (
    <BlockLayoutCtx.Provider value={value}>
      {children}
    </BlockLayoutCtx.Provider>
  )
}

export function useBlockLayout() {
  const ctx = useContext(BlockLayoutCtx)
  if (!ctx) throw new Error('useBlockLayout must be used within BlockLayoutProvider')
  return ctx
}
