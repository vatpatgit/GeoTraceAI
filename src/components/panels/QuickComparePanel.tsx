'use client'

import { useEffect, useMemo, useState } from 'react'
import { CalendarRange, X } from 'lucide-react'
import { api, API_BASE, ApiError, authHeaders, type BBox, type Scene } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, Field, inputCls, Segmented } from '@/components/ui/kit'

const MAX_SPAN_DEG = 0.5
const MAX_CLOUD_PCT = 40
const DAY = 86_400_000
const iso = (t: number) => new Date(t).toISOString().slice(0, 10)
const toT = (d: string) => Date.parse(`${d}T00:00:00Z`)

async function fetchPreview(scene: Scene, bbox: BBox): Promise<string> {
  const res = await fetch(`${API_BASE}/sentinel/preview`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ product_id: scene.product_id, acquired_at: scene.acquired_at, bbox, width: 2048 }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail?.message ?? (typeof body?.detail === 'string' ? body.detail : `Image retrieval failed (${res.status}).`))
  }
  return URL.createObjectURL(await res.blob())
}

/** Pick a region or type coordinates, give two dates: retrieve one Sentinel-2 image per date and compare them on the map. */
export default function QuickComparePanel() {
  const regions = useAppStore((s) => s.regions)
  const prefill = useAppStore((s) => s.quickPrefill)
  const setPrefill = useAppStore((s) => s.setQuickPrefill)
  const qc = useAppStore((s) => s.quickCompare)
  const setQc = useAppStore((s) => s.setQuickCompare)
  const quickShow = useAppStore((s) => s.quickShow)
  const setQuickShow = useAppStore((s) => s.setQuickShow)
  const viewMode = useAppStore((s) => s.viewMode)
  const setViewMode = useAppStore((s) => s.setViewMode)
  const setActiveAnalysis = useAppStore((s) => s.setActiveAnalysis)
  const requestFly = useAppStore((s) => s.requestFly)
  const setLeftPanel = useAppStore((s) => s.setLeftPanel)
  const provider = useAppStore((s) => s.system?.sentinel[0] ?? null)

  const today = iso(Date.now())
  const [b, setB] = useState({ w: '', s: '', e: '', n: '' })
  const [d1, setD1] = useState(iso(Date.now() - 365 * DAY))
  const [d2, setD2] = useState(iso(Date.now() - 20 * DAY))
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [label, setLabel] = useState<string | null>(null)

  useEffect(() => {
    if (!prefill) return
    setB({ w: String(prefill.bbox[0]), s: String(prefill.bbox[1]), e: String(prefill.bbox[2]), n: String(prefill.bbox[3]) })
    setLabel(prefill.name)
    setPrefill(null)
  }, [prefill, setPrefill])

  const nums = [b.w, b.s, b.e, b.n].map((v) => (v.trim() === '' ? NaN : Number(v)))
  const gapDays = (toT(d2) - toT(d1)) / DAY
  const problem = useMemo(() => {
    if (nums.some((n) => !Number.isFinite(n))) return 'Enter west, south, east and north as numbers.'
    const [w, s, e, n] = nums
    if (w < -180 || e > 180 || s < -85 || n > 85) return 'Longitude must be within ±180 and latitude within ±85.'
    if (w >= e || s >= n) return 'West must be less than east and south less than north.'
    if (e - w > MAX_SPAN_DEG || n - s > MAX_SPAN_DEG) return `The box may be at most ${MAX_SPAN_DEG}° wide and tall (about 50 km).`
    if (!d1 || !d2) return 'Choose both dates.'
    if (d1 > today || d2 > today) return 'Dates cannot be in the future.'
    if (gapDays < 3) return 'The second date must be at least 3 days after the first.'
    if (provider && provider.imagery !== 'available') return 'Imagery retrieval is not configured on the server (Sentinel credentials missing).'
    return null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b, d1, d2, provider])

  async function run() {
    if (problem) return
    const bbox = nums as BBox
    setError(null); setBusy('Searching Sentinel-2 scenes…')
    try {
      const win = Math.max(1, Math.min(10, Math.floor((gapDays - 1) / 2)))
      const r = await api.sentinel.search({
        bbox, max_cloud_cover_pct: MAX_CLOUD_PCT, limit: 40,
        before: { start: iso(toT(d1) - win * DAY), end: iso(toT(d1) + win * DAY) },
        after: { start: iso(toT(d2) - win * DAY), end: iso(toT(d2) + win * DAY) },
      })
      const closest = (list: Scene[], d: string, suggested: string | null) => {
        const ok = list.filter((x) => x.coverage_of_aoi_pct === null || x.coverage_of_aoi_pct >= 90)
        const pool = ok.length ? ok : list
        return pool.slice().sort((a, c) => Math.abs(Date.parse(a.acquired_at) - toT(d)) - Math.abs(Date.parse(c.acquired_at) - toT(d)) || (a.cloud_cover_pct ?? 100) - (c.cloud_cover_pct ?? 100))[0]
          ?? list.find((x) => x.product_id === suggested)
      }
      const sb = closest(r.before, d1, r.suggested_before)
      const sa = closest(r.after, d2, r.suggested_after)
      if (!sb) throw new Error(`No Sentinel-2 scene within ±${win} days of ${d1} with at most ${MAX_CLOUD_PCT}% cloud. Try another date.`)
      if (!sa) throw new Error(`No Sentinel-2 scene within ±${win} days of ${d2} with at most ${MAX_CLOUD_PCT}% cloud. Try another date.`)
      setBusy(`Downloading the ${formatDate(sb.acquired_at)} image…`)
      const ub = await fetchPreview(sb, bbox)
      setBusy(`Downloading the ${formatDate(sa.acquired_at)} image…`)
      let ua: string
      try { ua = await fetchPreview(sa, bbox) } catch (e) { URL.revokeObjectURL(ub); throw e }
      setQc({
        bbox,
        before: { url: ub, date: sb.acquired_at, cloud: sb.cloud_cover_pct, productId: sb.product_id },
        after: { url: ua, date: sa.acquired_at, cloud: sa.cloud_cover_pct, productId: sa.product_id },
      })
      setActiveAnalysis(null) // the two dates are an independent comparison: don't draw another analysis' polygons over them
      setViewMode('compare')
      requestFly({ bbox })
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : 'Could not retrieve the images.')
    } finally { setBusy(null) }
  }

  return (
    <aside aria-label="Compare two dates" className="panel absolute bottom-9 left-14 top-3 z-20 flex w-80 flex-col rounded-md shadow-2xl shadow-black/50">
      <header className="hairline-b flex items-center justify-between px-3 py-2">
        <h2 className="label flex items-center gap-1.5"><CalendarRange className="h-3.5 w-3.5" aria-hidden /> Compare two dates</h2>
        <button onClick={() => setLeftPanel(null)} aria-label="Close compare panel" className="focus-ring rounded text-slate-500 hover:text-slate-200"><X className="h-3.5 w-3.5" /></button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <Field label="Use a monitored region" htmlFor="qc-region">
          <select id="qc-region" className={inputCls} value="" onChange={(e) => {
            const r = regions.find((x) => x.id === e.target.value)
            const g = r?.geometry as { coordinates?: unknown } | null | undefined
            if (!r || !g?.coordinates) return
            const pts: number[][] = []
            const walk = (c: unknown): void => { if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[]); else if (Array.isArray(c)) c.forEach(walk) }
            walk(g.coordinates)
            const xs = pts.map((p) => p[0]); const ys = pts.map((p) => p[1])
            setB({ w: String(Math.min(...xs)), s: String(Math.min(...ys)), e: String(Math.max(...xs)), n: String(Math.max(...ys)) })
            setLabel(r.name)
          }}>
            <option value="">Choose to fill the box…</option>
            {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        <div>
          <div className="label mb-1">Area (decimal degrees){label ? <span className="ml-1 normal-case text-slate-500">· {label}</span> : null}</div>
          <div className="grid grid-cols-2 gap-2">
            {([['w', 'West (lon)'], ['s', 'South (lat)'], ['e', 'East (lon)'], ['n', 'North (lat)']] as const).map(([k, l]) => (
              <Field key={k} label={l} htmlFor={`qc-${k}`}><input id={`qc-${k}`} inputMode="decimal" className={`${inputCls} font-mono`} value={b[k]} onChange={(e) => { setB({ ...b, [k]: e.target.value }); setLabel(null) }} /></Field>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="First date" htmlFor="qc-d1"><input id="qc-d1" type="date" max={today} className={inputCls} value={d1} onChange={(e) => setD1(e.target.value)} /></Field>
          <Field label="Second date" htmlFor="qc-d2"><input id="qc-d2" type="date" max={today} className={inputCls} value={d2} onChange={(e) => setD2(e.target.value)} /></Field>
        </div>
        <p className="text-2xs text-slate-500">The scene closest to each date (within about ±10 days, at most 40% cloud) is used. Sentinel-2 revisits every ~5 days, so an exact-day image may not exist.</p>
        {problem && (b.w || b.s || b.e || b.n) && <p role="alert" className="text-2xs text-amber-300">{problem}</p>}
        <Button tone="accent" className="w-full py-2" disabled={!!problem} loading={!!busy} onClick={() => void run()}>Retrieve images and compare</Button>
        {busy && <p role="status" className="text-2xs text-slate-400">{busy}</p>}
        {error && <p role="alert" className="rounded border border-red-500/30 bg-red-500/[0.07] px-2.5 py-1.5 text-xs text-red-300">{error}</p>}

        {qc && (
          <div className="space-y-2 rounded-md border border-white/[0.08] bg-black/20 p-2.5 text-xs">
            <div className="flex items-center justify-between"><span className="label">Retrieved (Sentinel-2 L2A, true colour)</span><Button tone="ghost" className="px-1.5 py-0.5" onClick={() => setQc(null)}>Clear</Button></div>
            {([['Before', qc.before], ['After', qc.after]] as const).map(([name, sc]) => (
              <div key={name} className="flex items-center justify-between gap-2 font-mono text-2xs text-slate-300">
                <span>{name}: {formatDate(sc.date)}</span>
                <span className="text-slate-500">{sc.cloud === null ? 'cloud ?' : `${sc.cloud.toFixed(1)}% cloud`}</span>
              </div>
            ))}
            <Chip title="Product ids are kept for provenance">{qc.before.productId.slice(0, 24)}…</Chip>
            {viewMode === 'globe' && (
              <Segmented label="Globe image" size="sm" value={quickShow} onChange={setQuickShow} options={[{ value: 'before', label: 'Before' }, { value: 'after', label: 'After' }]} />
            )}
            <p className="text-2xs text-slate-500">Use the Compare view and drag the slider. In 2D the after image is shown; in 3D switch between before and after above. Images are display previews, not analysis-grade rasters; run an analysis for change detection.</p>
          </div>
        )}
      </div>
    </aside>
  )
}
