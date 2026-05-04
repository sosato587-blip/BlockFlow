'use client'

/**
 * URL text input + file picker that auto-uploads to /api/m/upload and
 * fills the URL field. Used wherever a block / mobile screen accepts
 * an image or video URL — lets users skip the round-trip through the
 * R2 gallery for one-shot uploads.
 *
 * Behavior:
 *   - URL textbox is the source of truth (controlled by ``value`` /
 *     ``onChange``). The uploaded URL flows back through the same prop.
 *   - "Upload" button opens a file picker; on selection the file is
 *     base64-encoded and POSTed to /api/m/upload, which proxies to
 *     tmpfiles.org and returns a public URL (~1h TTL on the free tier).
 *   - Drag-and-drop: drop a file anywhere on the component to trigger
 *     the same upload path.
 *   - Progress: shows "Uploading 12 MB..." while in flight; flips to
 *     a green check + "Uploaded (size MB)" on success; red error
 *     message on failure (kept until next attempt).
 *
 * Backend assumes data URI ≤ 100 MB raw (matches m_routes m_upload's
 * post-2026-05-02 limit). For larger files, the upload errors with
 * "blob size out of range" and the user falls back to the R2 gallery.
 */

import { useCallback, useRef, useState, type DragEvent } from 'react'
import { Loader2, Upload, X, Check } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

const UPLOAD_ENDPOINT = '/api/m/upload'
const MAX_BYTES = 100 * 1024 * 1024 // matches backend ceiling

export interface UrlOrFileInputProps {
  /** Current URL value (controlled). */
  value: string
  /** Called when the URL changes — either via direct typing or a finished upload. */
  onChange: (url: string) => void
  /** ``image/*`` or ``video/*`` — drives the file picker + drag-validate. */
  accept?: string
  /** Placeholder shown in the URL textbox. */
  placeholder?: string
  /** Optional className for the outermost wrapper. */
  className?: string
  /** Disable the entire component (e.g. while a parent is busy). */
  disabled?: boolean
  /** Custom upload-button label. Defaults to "Upload". */
  uploadLabel?: string
}

type UploadStatus =
  | { kind: 'idle' }
  | { kind: 'reading'; file: File }
  | { kind: 'uploading'; file: File; sizeMB: number }
  | { kind: 'done'; sizeMB: number }
  | { kind: 'error'; message: string }

function formatMB(bytes: number): number {
  return Math.round((bytes / (1024 * 1024)) * 10) / 10
}

async function fileToDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error || new Error('read failed'))
    reader.readAsDataURL(file)
  })
}

export function UrlOrFileInput({
  value,
  onChange,
  accept,
  placeholder = 'https://... or use Upload',
  className = '',
  disabled = false,
  uploadLabel = 'Upload',
}: UrlOrFileInputProps): React.ReactElement {
  const [status, setStatus] = useState<UploadStatus>({ kind: 'idle' })
  const [isDragOver, setIsDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const handleFile = useCallback(
    async (file: File) => {
      if (file.size > MAX_BYTES) {
        setStatus({
          kind: 'error',
          message: `File too large (${formatMB(file.size)} MB). Max 100 MB.`,
        })
        return
      }
      setStatus({ kind: 'reading', file })
      let dataUri: string
      try {
        dataUri = await fileToDataUri(file)
      } catch (e) {
        setStatus({ kind: 'error', message: `Read failed: ${e instanceof Error ? e.message : String(e)}` })
        return
      }
      const sizeMB = formatMB(file.size)
      setStatus({ kind: 'uploading', file, sizeMB })
      try {
        const res = await fetch(UPLOAD_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data: dataUri, filename: file.name }),
        })
        const data = await res.json()
        if (!data?.ok || !data.url) {
          setStatus({ kind: 'error', message: data?.error || `Upload failed (HTTP ${res.status})` })
          return
        }
        onChange(String(data.url))
        setStatus({ kind: 'done', sizeMB })
      } catch (e) {
        setStatus({
          kind: 'error',
          message: `Upload failed: ${e instanceof Error ? e.message : String(e)}`,
        })
      }
    },
    [onChange]
  )

  const onPick = () => inputRef.current?.click()
  const onPickerChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
    if (inputRef.current) inputRef.current.value = ''
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)
    if (disabled) return
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!disabled) setIsDragOver(true)
  }
  const onDragLeave = () => setIsDragOver(false)

  const busy = status.kind === 'reading' || status.kind === 'uploading'

  return (
    <div
      className={`space-y-1 ${className} ${isDragOver ? 'ring-1 ring-orange-400/50 rounded-md p-1 -m-1' : ''}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
    >
      <div className="flex items-center gap-1.5">
        <Input
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            if (status.kind === 'done' || status.kind === 'error') {
              setStatus({ kind: 'idle' })
            }
          }}
          placeholder={placeholder}
          disabled={disabled || busy}
          className="h-8 text-xs font-mono flex-1 min-w-0"
        />
        {value && !busy && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => {
              onChange('')
              setStatus({ kind: 'idle' })
            }}
            disabled={disabled}
            className="shrink-0 h-7 w-7"
            aria-label="Clear URL"
          >
            <X className="w-3.5 h-3.5" />
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onPick}
          disabled={disabled || busy}
          className="shrink-0 h-7 text-[11px] gap-1"
        >
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
          {uploadLabel}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={onPickerChange}
          className="hidden"
        />
      </div>

      {status.kind === 'reading' && (
        <p className="text-[10px] text-muted-foreground">Reading {status.file.name}...</p>
      )}
      {status.kind === 'uploading' && (
        <p className="text-[10px] text-cyan-300">
          Uploading {status.sizeMB} MB — keep this tab open until the URL appears…
        </p>
      )}
      {status.kind === 'done' && (
        <p className="text-[10px] text-emerald-400 flex items-center gap-1">
          <Check className="w-3 h-3" /> Uploaded ({status.sizeMB} MB) — URL filled in. tmpfiles links
          expire ~1 hour, so submit your job soon.
        </p>
      )}
      {status.kind === 'error' && (
        <p className="text-[10px] text-red-400">{status.message}</p>
      )}
    </div>
  )
}
