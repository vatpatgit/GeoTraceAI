'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Minus, Plus, Maximize2 } from 'lucide-react'
import { api, ApiError, type PlainChangeCollection } from '@/lib/api'
import { formatArea } from '@/lib/format'
import { useAppStore, type PlainImage } from '@/store/useAppStore'
import { Button, EmptyBlock, Segmented, Spinner, Switch } from '@/components/ui/kit'

const MIN_Z = 1
const MAX_Z = 16

function ringsToPath(coords: number[][][]): string {
  return coords.map((ring) => ring.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ') + ' Z').join(' ')
}

/** Highlights drawn in image-pixel space over the after image. */
function Changes({ fc, size }: { fc: PlainChangeCollection; size: [number, number] }) {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none" aria-label="Detected changes">
      {fc.features.map((f) => (
        <path key={f.id} d={ringsToPath(f.geometry.coordinates)} fill="rgba(244,63,94,0.5)" stroke="#FDE047" strokeWidth={2.5} vectorEffect="non-scaling-stroke" fillRule="evenodd" />
      ))}
    </svg>
  )
}

/**
 * Before / after comparison of two ordinary images (no coordinates, no map): shared zoom + pan, slider or side-by-side, and the same ML change
 * switch as the map comparison. Detections are drawn in image-pixel space on the after image.
 */
export default function ImageCompareView() {
  const pair = useAppStore((s) => s.plainCompare)
  const [layout, setLayout] = useState<'slider' | 'side'>('slider')
  const [pos, setPos] = useState(0.5)
  const [view, setView] = useState({ z: 1, x: 0, y: 0 })
  const [show, setShow] = useState(false)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [fc, setFc] = useState<PlainChangeCollection | null>(null)
  const [pixel, setPixel] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(true)
  const stage = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)
  const sliding = useRef(false)

  const size = useMemo<[number, number] | null>(() => (pair ? [pair.before.width, pair.before.height] : null), [pair])
  useEffect(() => { setFc(null); setShow(false); setStatus('idle'); setError(null); setView({ z: 1, x: 0, y: 0 }) }, [pair])

  const run = useCallback(async (pixelSizeM: number | null) => {
    if (!pair) return
    setStatus('loading'); setError(null)
    try {
      const data = await api.imagery.plainMlChanges(pair.before.file, pair.after.file, { pixelSizeM })
      setFc(data); setStatus('ready')
    } catch (e) { setStatus('error'); setShow(false); setError(e instanceof ApiError ? e.message : 'Change detection failed.') }
  }, [pair])

  async function toggle(on: boolean) {
    setShow(on)
    if (on && !fc && status !== 'loading') await run(Number(pixel) > 0 ? Number(pixel) : null)
  }

  // zoom around the cursor; pan by dragging
  const clamp = useCallback((v: { z: number; x: number; y: number }) => {
    const el = stage.current
    const w = el?.clientWidth ?? 0; const h = el?.clientHeight ?? 0
    const z = Math.min(MAX_Z, Math.max(MIN_Z, v.z))
    return { z, x: Math.min(0, Math.max(w - w * z, v.x)), y: Math.min(0, Math.max(h - h * z, v.y)) }
  }, [])
  const zoomAt = useCallback((factor: number, cx: number, cy: number) => {
    setView((v) => {
      const z = Math.min(MAX_Z, Math.max(MIN_Z, v.z * factor))
      const k = z / v.z
      return clamp({ z, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k })
    })
  }, [clamp])
  useEffect(() => {
    const el = stage.current
    if (!el) return
    const onWheel = (e: WheelEvent) => { e.preventDefault(); const r = el.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top) }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAt, pair, layout])

  const aspect = useMemo(() => (size ? size[0] / size[1] : 1), [size])
  if (!pair || !size) {
    return <div className="absolute inset-0 flex items-center justify-center"><EmptyBlock title="No images to compare" hint={<>Upload two images (PNG, JPG, WebP, BMP, GIF) on <Link href="/analyses/new" className="text-accent hover:underline">New analysis</Link> and the comparison opens here.</>} /></div>
  }

  const meta = fc?.metadata
  const innerStyle = { transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})`, transformOrigin: '0 0' } as const

  function Layer({ img, label, clipRightPct, withChanges, accent }: { img: PlainImage; label: string; clipRightPct?: number; withChanges?: boolean; accent?: boolean }) {
    return (
      <div className="absolute inset-0" style={{ ...innerStyle, ...(clipRightPct !== undefined ? { clipPath: `inset(0 ${clipRightPct}% 0 0)` } : {}) }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={img.url} alt={label} draggable={false} className="absolute inset-0 h-full w-full select-none object-fill" />
        {withChanges && show && fc && <Changes fc={fc} size={size!} />}
      </div>
    )
  }

  const fit = (child: React.ReactNode) => (
    <div className="flex h-full w-full items-center justify-center" style={{ containerType: 'size' }}>
      <div className="relative" style={{ width: `min(100cqw, calc(100cqh * ${aspect}))`, aspectRatio: String(aspect) }}>{child}</div>
    </div>
  )

  const frame = (children: React.ReactNode, role: 'single' | 'left' | 'right') => (
    <div ref={role === 'right' ? undefined : stage} className="relative h-full min-h-0 w-full cursor-grab overflow-hidden active:cursor-grabbing"
      onPointerDown={(e) => { if (sliding.current) return; drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) }}
      onPointerMove={(e) => { const d = drag.current; if (d) setView((v) => clamp({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y })) }}
      onPointerUp={() => { drag.current = null }}>
      {children}
    </div>
  )

  return (
    <div className="absolute inset-0 flex flex-col bg-ink-950">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[color:var(--line)] px-3 py-2">
        <div className="flex items-center gap-2">
          <Segmented label="Comparison layout" size="sm" value={layout} onChange={setLayout} options={[{ value: 'slider', label: 'Slider' }, { value: 'side', label: 'Side by side' }]} />
          <div className="flex items-center gap-0.5">
            <Button tone="ghost" aria-label="Zoom in" onClick={() => { const el = stage.current; zoomAt(1.4, (el?.clientWidth ?? 0) / 2, (el?.clientHeight ?? 0) / 2) }}><Plus className="h-3.5 w-3.5" /></Button>
            <Button tone="ghost" aria-label="Zoom out" onClick={() => { const el = stage.current; zoomAt(1 / 1.4, (el?.clientWidth ?? 0) / 2, (el?.clientHeight ?? 0) / 2) }}><Minus className="h-3.5 w-3.5" /></Button>
            <Button tone="ghost" aria-label="Reset view" onClick={() => setView({ z: 1, x: 0, y: 0 })}><Maximize2 className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-2xs text-slate-400" title="Optional: ground size of one pixel. Without it areas are shown as a share of the image.">
            Pixel size (m)
            <input aria-label="Pixel size in metres" inputMode="decimal" value={pixel} onChange={(e) => setPixel(e.target.value)} placeholder="optional" className="focus-ring w-20 rounded border border-[color:var(--line-strong)] bg-black/30 px-1.5 py-0.5 font-mono text-2xs text-slate-100" />
          </label>
          {fc && <Button tone="ghost" onClick={() => void run(Number(pixel) > 0 ? Number(pixel) : null)} disabled={status === 'loading'}>Re-run</Button>}
          <label className="flex items-center gap-1.5 text-2xs text-slate-300" title="Run the learned change-detection model on the two images and highlight what it flags on the after image">
            {status === 'loading' ? <Spinner className="h-3 w-3" label="Detecting changes" /> : null}
            ML changes
            <Switch checked={show} onChange={(v) => void toggle(v)} label="Show changes detected by the ML model" disabled={status === 'loading'} />
          </label>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <div className="absolute inset-0 p-2">
          {layout === 'slider' ? fit(
            frame(
              <>
                <Layer img={pair.after} label="After image" withChanges />
                <Layer img={pair.before} label="Before image" clipRightPct={(1 - pos) * 100} />
                <div className="pointer-events-none absolute left-2 top-2 z-10 rounded border border-[color:var(--line-strong)] bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-slate-300">Before · {pair.before.name}</div>
                <div className="pointer-events-none absolute right-2 top-2 z-10 rounded border border-accent/30 bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-accent">After · {pair.after.name}</div>
                <div role="slider" tabIndex={0} aria-label="Before and after comparison position" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pos * 100)}
                  onKeyDown={(e) => { if (e.key === 'ArrowLeft') setPos((p) => Math.max(0, p - (e.shiftKey ? 0.1 : 0.02))); if (e.key === 'ArrowRight') setPos((p) => Math.min(1, p + (e.shiftKey ? 0.1 : 0.02))) }}
                  onPointerDown={(e) => { e.stopPropagation(); sliding.current = true; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) }}
                  onPointerMove={(e) => { if (!sliding.current) return; const r = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect(); setPos(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))) }}
                  onPointerUp={() => { sliding.current = false }}
                  className="focus-ring absolute bottom-0 top-0 z-20 -ml-3 flex w-6 cursor-ew-resize items-center justify-center" style={{ left: `${pos * 100}%` }}>
                  <div className="h-full w-px bg-accent shadow-[0_0_10px_rgba(110,231,160,0.7)]" />
                  <div className="absolute flex h-8 w-5 items-center justify-center rounded-full border border-accent/70 bg-ink-900 text-accent shadow-lg"><span className="font-mono text-[10px] leading-none">&#8660;</span></div>
                </div>
              </>, 'single'))
          : (
            <div className="grid h-full grid-cols-2 gap-2">
              {fit(frame(<><Layer img={pair.before} label="Before image" /><div className="pointer-events-none absolute left-2 top-2 z-10 rounded border border-[color:var(--line-strong)] bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-slate-300">Before · {pair.before.name}</div></>, 'left'))}
              {fit(frame(<><Layer img={pair.after} label="After image" withChanges /><div className="pointer-events-none absolute right-2 top-2 z-10 rounded border border-accent/30 bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-accent">After · {pair.after.name}</div></>, 'right'))}
            </div>
          )}
        </div>

        <div className="pointer-events-none absolute bottom-3 left-1/2 z-30 flex -translate-x-1/2 flex-col items-center gap-1.5">
          {status === 'loading' && <div role="status" className="pointer-events-auto rounded border border-[color:var(--line-strong)] bg-ink-900/90 px-2 py-1 text-2xs text-slate-300">Running the change-detection model…</div>}
          {error && <div role="alert" className="pointer-events-auto max-w-md rounded border border-red-500/30 bg-ink-900/95 px-2 py-1 text-2xs text-red-300">{error}</div>}
          {show && meta && (
            <div role="status" className="pointer-events-auto max-w-lg rounded border border-[color:var(--line-strong)] bg-ink-900/95 px-2.5 py-2 text-2xs text-slate-300">
              <div className="flex items-start justify-between gap-2">
                <span><span className="font-mono text-slate-100">{meta.feature_count}</span> area{meta.feature_count === 1 ? '' : 's'} flagged · <span className="font-mono text-slate-100">{(meta.stats.changed_fraction * 100).toFixed(2)}%</span> of the image
                  {meta.pixel_size_known && meta.total_changed_area_m2 !== null ? ` · ${formatArea(meta.total_changed_area_m2)}` : ''}</span>
                <button onClick={() => setDetailsOpen(!detailsOpen)} aria-expanded={detailsOpen} className="focus-ring shrink-0 rounded px-1 text-slate-400 hover:text-slate-100">{detailsOpen ? 'Hide details' : 'Details'}</button>
              </div>
              {detailsOpen && (<>
                {meta.feature_count > 0 && (
                  <ul className="mt-1.5 space-y-0.5" aria-label="Flagged areas by size">
                    {meta.stats.size_classes.map((c) => (
                      <li key={c.label} className="flex items-center gap-2">
                        <span className="w-32 shrink-0 text-slate-400">{c.label}</span>
                        <span className="h-1.5 flex-1 rounded-full bg-white/[0.07]"><span className="block h-full rounded-full bg-rose-400" style={{ width: `${(c.count / Math.max(...meta.stats.size_classes.map((x) => x.count), 1)) * 100}%` }} /></span>
                        <span className="w-8 text-right font-mono text-slate-200">{c.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-1.5 text-slate-500">Model: {meta.model_name ?? meta.model_id}. {meta.model_choice_reason}</div>
                {meta.warnings.map((w) => <p key={w} className="mt-0.5 text-amber-200/80">{w}</p>)}
                <span className="mt-0.5 block text-amber-200/80">{meta.disclaimer}</span>
              </>)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
