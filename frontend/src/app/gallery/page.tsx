'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { fetchR2Images, type R2Image } from '@/lib/api'

const PAGE_SIZE = 48

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function isVideo(filename: string): boolean {
  const lower = filename.toLowerCase()
  return lower.endsWith('.mp4') || lower.endsWith('.webm')
}

export default function GalleryPage() {
  const [images, setImages] = useState<R2Image[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [selectedImage, setSelectedImage] = useState<R2Image | null>(null)

  const offset = (page - 1) * PAGE_SIZE

  const loadImages = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchR2Images(PAGE_SIZE, offset)
      if (!data.ok) {
        setError(data.error || 'Failed to load images')
        return
      }
      setImages(data.items)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load images')
    } finally {
      setIsLoading(false)
    }
  }, [offset])

  useEffect(() => {
    loadImages()
  }, [loadImages])

  // Client-side filter on loaded images
  const filteredImages = useMemo(() => {
    if (!filter.trim()) return images
    const lower = filter.toLowerCase()
    return images.filter((img) => img.filename.toLowerCase().includes(lower))
  }, [images, filter])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const canGoPrev = page > 1
  const canGoNext = page < totalPages

  return (
    <main className="mx-auto max-w-7xl px-4 pt-20 pb-6">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold text-foreground">R2 Gallery</h1>
            <p className="text-sm text-muted-foreground">
              {isLoading ? 'Loading...' : `${total} files in R2 storage`}
            </p>
          </div>

          {/* Filter */}
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              placeholder="Filter by filename..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="pl-8 h-8 text-sm"
            />
            {filter && (
              <button
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setFilter('')}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
            {error}
            <Button variant="outline" size="sm" className="ml-4 h-7" onClick={loadImages}>
              Retry
            </Button>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <p className="text-sm text-muted-foreground">Loading images from R2...</p>
          </div>
        )}

        {/* Empty */}
        {!isLoading && !error && filteredImages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 space-y-2">
            <p className="text-muted-foreground">
              {filter ? 'No images match your filter.' : 'No images found in R2 storage.'}
            </p>
          </div>
        )}

        {/* Image Grid */}
        {!isLoading && filteredImages.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 gap-3">
            {filteredImages.map((img) => (
              <button
                key={img.key}
                className="group relative rounded-lg border border-border/50 bg-card/50 overflow-hidden hover:border-primary/50 hover:bg-card transition-all cursor-pointer text-left"
                onClick={() => setSelectedImage(img)}
              >
                <div className="aspect-square relative bg-muted/30">
                  {isVideo(img.filename) ? (
                    <video
                      src={img.url}
                      muted
                      loop
                      playsInline
                      onMouseEnter={(e) => e.currentTarget.play()}
                      onMouseLeave={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0 }}
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={img.url}
                      alt={img.filename}
                      loading="lazy"
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  )}
                </div>
                <div className="p-2 space-y-0.5">
                  <p className="text-xs text-foreground truncate" title={img.filename}>
                    {img.filename}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {formatDate(img.last_modified)} &middot; {formatFileSize(img.size)}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Pagination */}
        {!isLoading && total > PAGE_SIZE && (
          <div className="flex items-center justify-between pt-2">
            <p className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8 px-3"
                disabled={!canGoPrev}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="size-4" />
                Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 px-3"
                disabled={!canGoNext}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Lightbox Dialog */}
      <Dialog open={!!selectedImage} onOpenChange={(open) => !open && setSelectedImage(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] p-0 overflow-hidden bg-card border-border">
          <DialogTitle className="sr-only">
            {selectedImage?.filename || 'Image preview'}
          </DialogTitle>
          {selectedImage && (
            <div className="flex flex-col">
              <div className="relative flex-1 flex items-center justify-center bg-black/50 min-h-[300px] max-h-[70vh]">
                {isVideo(selectedImage.filename) ? (
                  <video
                    src={selectedImage.url}
                    controls
                    autoPlay
                    loop
                    className="max-w-full max-h-[70vh] object-contain"
                  />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={selectedImage.url}
                    alt={selectedImage.filename}
                    className="max-w-full max-h-[70vh] object-contain"
                  />
                )}
              </div>
              <div className="p-4 flex items-center justify-between border-t border-border/50">
                <div className="space-y-0.5 min-w-0 mr-4">
                  <p className="text-sm font-medium text-foreground truncate">
                    {selectedImage.filename}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(selectedImage.last_modified)} &middot; {formatFileSize(selectedImage.size)}
                  </p>
                </div>
                <a
                  href={selectedImage.url}
                  download={selectedImage.filename}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0"
                >
                  <Button variant="outline" size="sm" className="h-8 gap-1.5">
                    <Download className="w-3.5 h-3.5" />
                    Download
                  </Button>
                </a>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </main>
  )
}
