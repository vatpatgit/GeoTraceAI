'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Map as MlMap } from 'maplibre-gl'
import { formatDate } from '@/lib/format'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { canWrite } from '@/lib/auth'
import { formatArea } from '@/lib/format'
import { EmptyBlock, Segmented, Spinner, Switch } from '@/components/ui/kit'
import MapCanvas from './MapCanvas'

/**
 * Before/after split view: two MapLibre instances over the same extent.
 *  - bottom map = AFTER (interactive, owns the camera, polygons and selection)
 *  - top map    = BEFORE (non-interactive, clipped to the left of the slider, camera mirrored from the bottom map)
 * Because the top map has `pointer-events: none`, every interaction goes to the bottom map, so zoom/pan/selection
 * work across the entire canvas while the slider only changes what is *drawn*.
 */
const sceneLabel = (sc: { date: string; label?: string }): string => (sc.label ? (sc.date ? `${sc.label} · ${formatDate(sc.date)}` : sc.label) : formatDate(sc.date))

export default function CompareView() {
  const router = useRouter()
  const user = useAppStore((s) => s.authUser)
  const projectId = useAppStore((s) => s.activeProjectId)
  const upsert = useAppStore((s) => s.upsertAnalysis)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const setQc = useAppStore((s) => s.setQuickCompare)
  const toast = useAppStore((s) => s.toast)
  const [saving, setSaving] = useState(false)
  const [statsOpen, setStatsOpen] = useState(true)
  const analysis = useAppStore(selectActiveAnalysis)
  const qc = useAppStore((s) => s.quickCompare)
  const [layout, setLayout] = useState<'slider' | 'side'>('slider')
  const changes = useAppStore((s) => s.quickChanges)
  const setChanges = useAppStore((s) => s.setQuickChanges)
  const pos = useAppStore((s) => s.comparePosition)
  const setPos = useAppStore((s) => s.setComparePosition)
  const [after, setAfter] = useState<MlMap | null>(null)
  const [before, setBefore] = useState<MlMap | null>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  // mirror camera: after -> before (rAF-throttled, no feedback because the before map takes no input)
  useEffect(() => {
    if (!after || !before) return
    let raf = 0
    const sync = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const c = after.getCenter()
        before.jumpTo({ center: c, zoom: after.getZoom(), bearing: after.getBearing(), pitch: after.getPitch() })
      })
    }
    sync()
    after.on('move', sync)
    return () => { after.off('move', sync); if (raf) cancelAnimationFrame(raf) }
  }, [after, before])

  // side-by-side: both maps are interactive and follow each other
  useEffect(() => {
    if (layout !== 'side' || !after || !before) return
    let busy = false
    const follow = (from: MlMap, to: MlMap) => () => {
      if (busy) return
      busy = true
      to.jumpTo({ center: from.getCenter(), zoom: from.getZoom(), bearing: from.getBearing(), pitch: from.getPitch() })
      busy = false
    }
    const a = follow(after, before); const b = follow(before, after)
    after.on('move', a); before.on('move', b)
    return () => { after.off('move', a); before.off('move', b) }
  }, [layout, after, before])

  // frame the retrieved box when the side-by-side maps appear (they start from the stored camera)
  const bbox = qc?.bbox
  useEffect(() => {
    if (layout !== 'side' || !after || !before || !bbox) return
    const fit = (m: MlMap) => { m.resize(); m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40, duration: 0, maxZoom: 17 }) }
    const t = setTimeout(() => { fit(after); fit(before) }, 150)
    return () => clearTimeout(t)
  }, [layout, after, before, bbox])

  const update = useCallback((clientX: number) => {
    const el = wrap.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setPos((clientX - r.left) / r.width)
  }, [setPos])

  if (!qc && (!analysis || analysis.status !== 'completed')) {
    return <div className="absolute inset-0 flex items-center justify-center"><EmptyBlock title="Nothing to compare yet" hint="Use the Compare dates tool (calendar icon, left rail) to retrieve two Sentinel-2 images, or select a completed analysis." /></div>
  }

  async function toggleChanges(on: boolean) {
    if (!qc) return
    setChanges({ show: on })
    if (!on || changes.data || changes.status === 'loading') return
    setChanges({ status: 'loading', error: null })
    try {
      const data = qc.source?.kind === 'upload'
        ? await api.imagery.mlChanges({ before_asset_id: qc.source.beforeAssetId, after_asset_id: qc.source.afterAssetId, bbox: qc.bbox })
        : await api.sentinel.mlChanges({ bbox: qc.bbox, before_at: qc.before.date, after_at: qc.after.date })
      setChanges({ status: 'ready', data })
    } catch (e) { setChanges({ status: 'error', show: false, error: e instanceof ApiError ? e.message : 'Change detection failed.' }) }
  }
  const meta = changes.data?.metadata
  async function saveAsAnalysis() {
    if (!qc || !projectId) return
    setSaving(true)
    try {
      const detection = { method: 'learned_siamese', ...(meta?.model_id ? { model_id: meta.model_id } : {}) }
      let analysisId: string
      if (qc.source?.kind === 'upload') {
        const a = await api.analyses.create({ project_id: qc.source.projectId, name: `ML change: ${qc.before.label ?? 'before'} → ${qc.after.label ?? 'after'}`.slice(0, 160),
          before_asset_id: qc.source.beforeAssetId, after_asset_id: qc.source.afterAssetId, config: { detection }, input_type: 'upload' })
        analysisId = a.id
      } else {
        const [w, so, e, n] = qc.bbox
        const r = await api.sentinel.acquire({
          project_id: projectId, name: `ML change ${qc.before.date.slice(0, 10)} → ${qc.after.date.slice(0, 10)}`,
          aoi_geometry: { type: 'Polygon', coordinates: [[[w, so], [e, so], [e, n], [w, n], [w, so]]] },
          before_product_id: qc.before.productId, after_product_id: qc.after.productId, config: { detection },
        })
        analysisId = r.analysis_id
      }
      upsert(await api.analyses.get(analysisId))
      setQc(null)
      setActive(analysisId)
      toast('info', 'Saved as an analysis: the full-quality data is processed and the model re-runs on it. Progress is in the drawer.')
      router.push('/map')
    } catch (err) { toast('error', err instanceof ApiError ? err.message : 'Could not save the analysis.') } finally { setSaving(false) }
  }
  const toggle = qc ? (
    <div className="absolute left-1/2 top-3 z-30 flex -translate-x-1/2 flex-col items-center gap-1.5">
      <div className="flex items-center gap-2 rounded-md border border-[color:var(--line-strong)] bg-ink-900/90 p-0.5">
        <Segmented label="Comparison layout" size="sm" value={layout} onChange={setLayout} options={[{ value: 'slider', label: 'Slider' }, { value: 'side', label: 'Side by side' }]} />
        <label className="flex items-center gap-1.5 border-l border-[color:var(--line-strong)] pl-2 pr-1.5 text-2xs text-slate-300" title="Run the learned change-detection model on the two images and highlight what it flags on the after image">
          {changes.status === 'loading' ? <Spinner className="h-3 w-3" label="Detecting changes" /> : null}
          ML changes
          <Switch checked={changes.show} onChange={(v) => void toggleChanges(v)} label="Show changes detected by the ML model" disabled={changes.status === 'loading'} />
        </label>
      </div>
    </div>
  ) : null
  const notice = qc ? (
    <div className="pointer-events-none absolute bottom-3 left-1/2 z-30 flex -translate-x-1/2 flex-col items-center gap-1.5">
      {changes.status === 'loading' && <div role="status" className="pointer-events-auto rounded border border-[color:var(--line-strong)] bg-ink-900/90 px-2 py-1 text-2xs text-slate-300">Running the change-detection model…</div>}
      {changes.error && <div role="alert" className="pointer-events-auto max-w-md rounded border border-red-500/30 bg-ink-900/95 px-2 py-1 text-2xs text-red-300">{changes.error}</div>}
      {changes.show && meta && (
        <div role="status" className="pointer-events-auto max-w-lg rounded border border-[color:var(--line-strong)] bg-ink-900/95 px-2.5 py-2 text-2xs text-slate-300">
          <div className="flex items-start justify-between gap-2">
            <span><span className="font-mono text-slate-100">{meta.feature_count}</span> area{meta.feature_count === 1 ? '' : 's'} flagged · {formatArea(meta.total_changed_area_m2)}
            {' '}(<span className="font-mono text-slate-100">{(meta.stats.changed_fraction * 100).toFixed(2)}%</span> of the {formatArea(meta.stats.analyzed_area_m2)} compared)
            {meta.masked_cloud_pct > 0 ? ` · ${meta.masked_cloud_pct}% masked (cloud, shadow, no data)` : ''}</span>
            <button onClick={() => setStatsOpen(!statsOpen)} aria-expanded={statsOpen} className="focus-ring shrink-0 rounded px-1 text-slate-400 hover:text-slate-100">{statsOpen ? 'Hide details' : 'Details'}</button>
          </div>
          {statsOpen && (<>
          {meta.feature_count > 0 && (
            <ul className="mt-1.5 space-y-0.5" aria-label="Flagged areas by size">
              {meta.stats.size_classes.map((c) => (
                <li key={c.label} className="flex items-center gap-2">
                  <span className="w-28 shrink-0 text-slate-400">{c.label}</span>
                  <span className="h-1.5 flex-1 rounded-full bg-white/[0.07]"><span className="block h-full rounded-full bg-rose-400" style={{ width: `${(c.count / Math.max(...meta.stats.size_classes.map((x) => x.count), 1)) * 100}%` }} /></span>
                  <span className="w-8 text-right font-mono text-slate-200">{c.count}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-1.5 text-slate-500">Model: {meta.model_name ?? meta.model_id} · fed at {meta.model_fed_at_m ?? '?'} m/px</div>
          <span className="mt-0.5 block text-amber-200/80">{meta.disclaimer}</span>
          {canWrite(user?.role) && projectId && (
            <button onClick={() => void saveAsAnalysis()} disabled={saving} className="focus-ring mt-2 rounded border border-accent-dim bg-accent-surface px-2 py-1 text-accent hover:bg-[#1a4430] disabled:opacity-50">
              {saving ? 'Saving…' : 'Save as analysis (alerts, exports, reports)'}
            </button>
          )}
          </>)}
        </div>
      )}
    </div>
  ) : null

  if (layout === 'side' && qc) {
    return (
      <div className="absolute inset-0 flex select-none gap-px bg-white/20">
        <div className="relative min-w-0 flex-1"><MapCanvas role="before" onMap={setBefore} /><div className="pointer-events-none absolute left-14 top-3 z-10 rounded border border-[color:var(--line-strong)] bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-slate-300">Before &middot; {sceneLabel(qc.before)}{qc.before.cloud !== null ? ` · ${qc.before.cloud.toFixed(0)}% cloud` : ''}</div></div>
        <div className="relative min-w-0 flex-1"><MapCanvas role="after" onMap={setAfter} /><div className="pointer-events-none absolute right-3 top-3 z-10 rounded border border-accent/30 bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-accent">After &middot; {sceneLabel(qc.after)}{qc.after.cloud !== null ? ` · ${qc.after.cloud.toFixed(0)}% cloud` : ''}</div></div>
        {toggle}
        {notice}
      </div>
    )
  }

  return (
    <div ref={wrap} className="absolute inset-0 select-none">
      {toggle}
      {notice}
      <MapCanvas role="after" onMap={setAfter} />
      <div className="pointer-events-none absolute inset-0" style={{ clipPath: `inset(0 ${(1 - pos) * 100}% 0 0)` }} aria-hidden>
        <MapCanvas role="before" interactive={false} onMap={setBefore} />
      </div>

      <div className="pointer-events-none absolute left-3 top-3 z-10 rounded border border-[color:var(--line-strong)] bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-slate-300">
        Before <span className="text-slate-500">&middot;</span> {qc ? sceneLabel(qc.before) : formatDate(analysis?.before_date)}
      </div>
      <div className="pointer-events-none absolute right-3 top-3 z-10 rounded border border-accent/30 bg-ink-900/85 px-2 py-1 font-mono text-2xs uppercase tracking-wider text-accent">
        After <span className="text-accent/50">&middot;</span> {qc ? sceneLabel(qc.after) : formatDate(analysis?.after_date)}
      </div>

      <div
        role="slider"
        tabIndex={0}
        aria-label="Before and after comparison position"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos * 100)}
        aria-orientation="horizontal"
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') { e.preventDefault(); setPos(pos - (e.shiftKey ? 0.1 : 0.02)) }
          if (e.key === 'ArrowRight') { e.preventDefault(); setPos(pos + (e.shiftKey ? 0.1 : 0.02)) }
          if (e.key === 'Home') setPos(0)
          if (e.key === 'End') setPos(1)
        }}
        onPointerDown={(e) => { dragging.current = true; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); update(e.clientX) }}
        onPointerMove={(e) => { if (dragging.current) update(e.clientX) }}
        onPointerUp={(e) => { dragging.current = false; (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId) }}
        className="focus-ring absolute bottom-0 top-0 z-20 -ml-3 flex w-6 cursor-ew-resize items-center justify-center"
        style={{ left: `${pos * 100}%` }}
      >
        <div className="h-full w-px bg-accent shadow-[0_0_10px_rgba(110,231,160,0.7)]" />
        <div className="absolute flex h-8 w-5 items-center justify-center rounded-full border border-accent/70 bg-ink-900 text-accent shadow-lg">
          <span className="font-mono text-[10px] leading-none">&#8660;</span>
        </div>
      </div>
    </div>
  )
}
