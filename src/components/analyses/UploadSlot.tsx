'use client'

import { useId, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileUp, Info, X } from 'lucide-react'
import { api, ApiError, type ImageryAsset } from '@/lib/api'
import type { PlainImage } from '@/store/useAppStore'
import { cn, formatBytes } from '@/lib/format'
import { Button, Chip, Field, inputCls, ProgressBar } from '@/components/ui/kit'

const ROLES = ['red', 'green', 'blue', 'nir'] as const

interface Props {
  title: string
  projectId: string
  asset: ImageryAsset | null
  onAsset: (a: ImageryAsset | null) => void
  /** Ordinary images (PNG / JPEG / WebP / BMP / GIF) are not uploaded; they stay in the browser and are compared without a map. */
  plain?: PlainImage | null
  onPlain?: (p: PlainImage | null) => void
}

export const PLAIN_IMAGE_RE = /\.(png|jpe?g|webp|bmp|gif)$/i
const isPlain = (f: File) => PLAIN_IMAGE_RE.test(f.name) || /^image\/(png|jpeg|webp|bmp|gif)$/i.test(f.type)

function readSize(url: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = () => reject(new Error('This file could not be read as an image.'))
    img.src = url
  })
}

/** One before/after upload: drag-drop, real upload progress, server validation report, band-role confirmation. */
export default function UploadSlot({ title, projectId, asset, onAsset, plain = null, onPlain }: Props) {
  const inputId = useId()
  const input = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bandMap, setBandMap] = useState<Record<string, number>>({})
  const ctrl = useRef<AbortController | null>(null)

  async function send(file: File) {
    setError(null)
    if (onPlain && isPlain(file)) {
      const url = URL.createObjectURL(file)
      try { onPlain({ file, url, name: file.name, ...(await readSize(url)) }) } catch (e) { URL.revokeObjectURL(url); setError((e as Error).message) }
      return
    }
    if (!/\.(tif|tiff)$/i.test(file.name)) { setError(onPlain ? 'Choose a GeoTIFF (.tif / .tiff) or an image (.png / .jpg / .jpeg / .webp / .bmp / .gif).' : 'Choose a GeoTIFF (.tif / .tiff). The file content is verified again on the server.'); return }
    setProgress(0)
    ctrl.current = new AbortController()
    try {
      const a = await api.imagery.upload(file, projectId, { onProgress: setProgress, signal: ctrl.current.signal })
      onAsset(a)
      setBandMap(a.band_map ?? {})
    } catch (e) {
      if ((e as Error).name === 'AbortError') setError('Upload cancelled.')
      else setError(e instanceof ApiError ? e.message : 'Upload failed.')
    } finally { setProgress(null) }
  }

  async function saveBands(next: Record<string, number>) {
    setBandMap(next)
    if (asset) {
      try { onAsset(await api.imagery.update(asset.id, { band_map: next })) } catch (e) { setError(e instanceof ApiError ? e.message : 'Invalid band mapping') }
    }
  }

  const uploading = progress !== null
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between"><h3 className="text-xs font-medium text-slate-200">{title}</h3>{(asset || plain) && <Button tone="ghost" className="px-1.5 py-0.5" onClick={() => { onAsset(null); onPlain?.(null); setError(null) }}><X className="h-3 w-3" aria-hidden /> Replace</Button>}</div>

      {!asset && !plain && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) void send(f) }}
          className={cn('flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-md border border-dashed px-4 py-5 text-center transition-colors', drag ? 'border-accent bg-accent/[0.06]' : 'border-white/15 bg-black/20')}
        >
          <FileUp className="h-5 w-5 text-slate-500" aria-hidden />
          {uploading ? (
            <div className="w-full max-w-[220px] space-y-1.5"><ProgressBar value={progress ?? 0} /><div className="font-mono text-2xs text-slate-400">{Math.round((progress ?? 0) * 100)}% - validating on the server after upload</div><Button tone="ghost" onClick={() => ctrl.current?.abort()}>Cancel</Button></div>
          ) : (
            <>
              <p className="text-xs text-slate-300">{onPlain ? 'Drop a GeoTIFF or an image (PNG, JPG, WebP…) here or' : 'Drop a GeoTIFF here or'}</p>
              <Button onClick={() => input.current?.click()}>Choose file</Button>
              <input ref={input} id={inputId} type="file" accept={onPlain ? '.tif,.tiff,image/tiff,.png,.jpg,.jpeg,.webp,.bmp,.gif,image/png,image/jpeg,image/webp,image/bmp,image/gif' : '.tif,.tiff,image/tiff'} className="sr-only" aria-label={`${title} GeoTIFF file`} onChange={(e) => { const f = e.target.files?.[0]; if (f) void send(f); e.target.value = '' }} />
            </>
          )}
        </div>
      )}
      {error && <p role="alert" className="rounded border border-red-500/30 bg-red-500/[0.07] px-2.5 py-1.5 text-xs text-red-300">{error}</p>}


      {plain && (
        <div className="space-y-2 rounded-md border border-white/[0.07] bg-black/20 p-2.5">
          <div className="flex items-center gap-1.5 text-xs text-slate-200"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-hidden /><span className="truncate">{plain.name}</span><span className="text-slate-500">{formatBytes(plain.file.size)}</span></div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={plain.url} alt={`${title} preview`} className="max-h-48 w-full rounded object-contain" />
          <p className="font-mono text-2xs text-slate-400">{plain.width} x {plain.height} px · ordinary image (no coordinates)</p>
        </div>
      )}
      {asset && (
        <div className="space-y-2 rounded-md border border-white/[0.07] bg-black/20 p-2.5">
          <div className="flex items-center gap-1.5 text-xs text-slate-200"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-hidden /><span className="truncate">{asset.original_filename}</span><span className="text-slate-500">{formatBytes(asset.size_bytes)}</span></div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-2xs text-slate-400">
            <dt>Size</dt><dd className="text-slate-200">{asset.width} x {asset.height} px, {asset.band_count} band{asset.band_count > 1 ? 's' : ''}</dd>
            <dt>CRS</dt><dd className="text-slate-200">{asset.crs_epsg ? `EPSG:${asset.crs_epsg}` : 'custom'}</dd>
            <dt>Resolution</dt><dd className="text-slate-200">{asset.pixel_size_m.toFixed(2)} m / px</dd>
            <dt>Type</dt><dd className="text-slate-200">{asset.dtype}{asset.nodata !== null ? `, NoData ${asset.nodata}` : ''}</dd>
          </dl>
          {asset.band_count >= 3 && (
            <div>
              <div className="label mb-1 flex items-center gap-1.5">Band roles {asset.band_map_confirmed ? <Chip tone="ok">confirmed</Chip> : <Chip tone="warn">assumed - please confirm</Chip>}</div>
              <div className="grid grid-cols-4 gap-1.5">
                {ROLES.map((r) => (
                  <label key={r} className="text-2xs text-slate-500">{r}
                    <select value={bandMap[r] ?? ''} onChange={(e) => { const n = { ...bandMap }; if (e.target.value) n[r] = Number(e.target.value); else delete n[r]; void saveBands(n) }} aria-label={`${title} ${r} band`} className="focus-ring mt-0.5 w-full rounded border border-white/10 bg-black/40 px-1 py-0.5 font-mono text-2xs text-slate-200">
                      <option value="">-</option>{Array.from({ length: asset.band_count }, (_, i) => <option key={i} value={i + 1}>{i + 1}{asset.band_descriptions?.[i] ? ` (${asset.band_descriptions[i]})` : ''}</option>)}
                    </select>
                  </label>
                ))}
              </div>
            </div>
          )}
          <ul className="space-y-1">
            {asset.warnings.map((w, i) => <li key={i} className={cn('flex gap-1.5 text-2xs', w.level === 'warning' ? 'text-amber-200' : 'text-slate-500')}>{w.level === 'warning' ? <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden /> : <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />}{w.message}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
