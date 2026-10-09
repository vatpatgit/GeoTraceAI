'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, Eye, Search, Wand2, X } from 'lucide-react'
import { api, API_BASE, ApiError, authHeaders, type DetectionMethod, type Position, type Scene, type SentinelSearchResult } from '@/lib/api'
import { cn, formatDate, formatPct } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, Field, inputCls, Spinner } from '@/components/ui/kit'
import AoiPickerMap from './AoiPickerMap'

const iso = (d: Date) => d.toISOString().slice(0, 10)
const days = (n: number) => { const d = new Date(); d.setUTCDate(d.getUTCDate() + n); return d }

function defaultWindows() {
  const after = { start: iso(days(-75)), end: iso(days(-5)) }
  const before = { start: iso(days(-75 - 365)), end: iso(days(-5 - 365)) }
  return { before, after }
}

function SceneRow({ s, selected, suggested, onSelect, onPreview }: { s: Scene; selected: boolean; suggested: boolean; onSelect: () => void; onPreview: () => void }) {
  const tiles = (s.properties.tile_ids as string[] | undefined)?.length ?? 1
  return (
    <li className={cn('flex items-center gap-3 border-b border-white/[0.05] px-3 py-1.5 text-xs last:border-b-0', selected && 'bg-accent/[0.07]')}>
      <input type="radio" checked={selected} onChange={onSelect} aria-label={`Select scene from ${formatDate(s.acquired_at)}`} />
      <span className="w-24 font-mono text-slate-200">{formatDate(s.acquired_at)}</span>
      <span className="w-20 font-mono text-slate-400" title="Cloud cover over the area (area-weighted across tiles)">{s.cloud_cover_pct === null ? 'cloud ?' : `${s.cloud_cover_pct.toFixed(1)}% cloud`}</span>
      <span className="w-24 font-mono text-slate-500" title="Share of the area covered by the scene">{s.coverage_of_aoi_pct === null ? '-' : `${s.coverage_of_aoi_pct.toFixed(0)}% cover`}</span>
      <span className="flex-1 truncate text-2xs text-slate-500">{s.platform ?? ''} &middot; {s.resolution_m} m &middot; {tiles} tile{tiles > 1 ? 's' : ''}</span>
      {suggested && <Chip tone="accent">rule pick</Chip>}
      <Button tone="ghost" className="px-1.5 py-0.5" onClick={onPreview} aria-label={`Preview scene from ${formatDate(s.acquired_at)}`}><Eye className="h-3 w-3" aria-hidden /> Preview</Button>
    </li>
  )
}

export interface RegionAoi { name: string; bbox: [number, number, number, number]; area_km2: number }

/** `region`: use a monitored region's bounding box instead of a picked centre + radius. */
export default function SentinelStep({ projectId, region }: { projectId: string; region?: RegionAoi }) {
  const router = useRouter()
  const system = useAppStore((s) => s.system)
  const upsert = useAppStore((s) => s.upsertAnalysis)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const setDrawerTab = useAppStore((s) => s.setDrawerTab)
  const setViewMode = useAppStore((s) => s.setViewMode)
  const toast = useAppStore((s) => s.toast)
  const provider = system?.sentinel[0] ?? null

  const [center, setCenter] = useState<Position | null>(null)
  const [lon, setLon] = useState('')
  const [lat, setLat] = useState('')
  const [radiusKm, setRadiusKm] = useState(2.5)
  const [win, setWin] = useState(defaultWindows)
  const [cloud, setCloud] = useState(30)
  const [method, setMethod] = useState<DetectionMethod>('spectral_cva')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SentinelSearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selB, setSelB] = useState<string | null>(null)
  const [selA, setSelA] = useState<string | null>(null)
  const [acquiring, setAcquiring] = useState(false)
  const [preview, setPreview] = useState<{ url: string; label: string } | null>(null)

  useEffect(() => { if (center) { setLon(String(center[0])); setLat(String(center[1])) } }, [center])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url) }, [preview])

  const valid = useMemo(() => {
    const lo = parseFloat(lon), la = parseFloat(lat)
    return !!region || (Number.isFinite(lo) && Number.isFinite(la) && Math.abs(la) <= 85 && Math.abs(lo) <= 180)
  }, [lon, lat, region])
  const datesOk = win.before.start <= win.before.end && win.after.start <= win.after.end && win.before.end < win.after.start
  const radiusM = radiusKm * 1000
  const canSearch = valid && datesOk && !busy && provider?.catalog === 'available'
  const canAcquire = provider?.imagery === 'available'

  function aoiBody() {
    if (region) return { bbox: region.bbox }
    return { center: [parseFloat(lon), parseFloat(lat)] as Position, radius_m: radiusM }
  }

  async function search() {
    setBusy(true); setError(null); setResult(null); setSelA(null); setSelB(null)
    try {
      const r = await api.sentinel.search({ ...aoiBody(), project_id: projectId, before: win.before, after: win.after, max_cloud_cover_pct: cloud, limit: 20 })
      setResult(r); setSelB(r.suggested_before); setSelA(r.suggested_after)
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Search failed') } finally { setBusy(false) }
  }

  async function acquire(auto: boolean) {
    if (!result) return
    setAcquiring(true); setError(null)
    try {
      const aoiGeometry = result.aoi_geometry
      const r = await api.sentinel.acquire({
        project_id: projectId, aoi_geometry: aoiGeometry, max_cloud_cover_pct: cloud, config: { detection: { method } },
        ...(auto ? { auto_select: true, before: win.before, after: win.after } : { before_product_id: selB ?? undefined, after_product_id: selA ?? undefined }),
      })
      const a = await api.analyses.get(r.analysis_id)
      upsert(a); setActive(a.id); setDrawerTab('progress')
      toast('info', 'Analysis queued: scenes are retrieved first, then change detection runs.')
      if (region) setViewMode('compare')
      router.push('/map')
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not start the acquisition') } finally { setAcquiring(false) }
  }

  async function showPreview(s: Scene) {
    if (!result) return
    const [w, so, e, n] = bboxOf(result.aoi_geometry)
    try {
      const res = await fetch(`${API_BASE}/sentinel/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ product_id: s.product_id, acquired_at: s.acquired_at, bbox: [w, so, e, n], width: 640 }) })
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail?.message ?? `Preview failed (${res.status})`)
      setPreview({ url: URL.createObjectURL(await res.blob()), label: `${formatDate(s.acquired_at)} - ${s.cloud_cover_pct?.toFixed(1) ?? '?'}% cloud` })
    } catch (e) { toast('error', (e as Error).message) }
  }

  const sel = (list: Scene[], id: string | null) => list.find((s) => s.product_id === id)

  return (
    <div className="space-y-5">
      <div role="status" className={cn('rounded-md border px-3 py-2 text-xs', provider?.imagery === 'available' ? 'border-emerald-400/20 bg-emerald-400/[0.04] text-emerald-200' : provider?.catalog === 'available' ? 'border-amber-400/25 bg-amber-400/[0.05] text-amber-200' : 'border-red-500/25 bg-red-500/[0.05] text-red-300')}>
        {provider ? <><strong className="font-medium">{provider.provider.toUpperCase()}</strong>: catalogue {provider.catalog.replace('_', ' ')}, imagery retrieval {provider.imagery.replace('_', ' ')}. {provider.detail}</> : 'Provider status unavailable.'}
        {provider && provider.imagery !== 'available' && ' You can search, but acquiring imagery needs server-side credentials; otherwise upload GeoTIFFs.'}
      </div>

      <section className="grid gap-5 md:grid-cols-2" aria-label="Area and dates">
        <div className="space-y-3">
          <h3 className="text-xs font-medium text-slate-200">1. Area of interest</h3>
          {region ? (
            <div className="rounded-md border border-white/[0.08] bg-black/20 p-3 text-xs text-slate-300">
              <div className="text-slate-100">{region.name}</div>
              <div className="mt-1 font-mono text-2xs text-slate-400">W {region.bbox[0].toFixed(4)} · S {region.bbox[1].toFixed(4)} · E {region.bbox[2].toFixed(4)} · N {region.bbox[3].toFixed(4)}</div>
              <div className="mt-1 text-2xs text-slate-500">Bounding box of the region, ~{region.area_km2.toLocaleString('en-US', { maximumFractionDigits: 1 })} km2{system && region.area_km2 > system.limits.max_aoi_km2 ? ` - exceeds the ${system.limits.max_aoi_km2.toLocaleString('en-US')} km2 limit` : ''}.</div>
            </div>
          ) : (<>
          <AoiPickerMap center={center} radiusM={radiusM} onPick={setCenter} />
          <p className="text-2xs text-slate-500">Click the map to set the centre, or type coordinates.</p>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Longitude" htmlFor="slon"><input id="slon" inputMode="decimal" value={lon} onChange={(e) => { setLon(e.target.value); const lo = parseFloat(e.target.value), la = parseFloat(lat); if (Number.isFinite(lo) && Number.isFinite(la)) setCenter([lo, la]) }} className={inputCls} placeholder="-62.30" /></Field>
            <Field label="Latitude" htmlFor="slat"><input id="slat" inputMode="decimal" value={lat} onChange={(e) => { setLat(e.target.value); const lo = parseFloat(lon), la = parseFloat(e.target.value); if (Number.isFinite(lo) && Number.isFinite(la)) setCenter([lo, la]) }} className={inputCls} placeholder="-10.90" /></Field>
            <Field label={`Radius ${radiusKm} km`} htmlFor="srad"><input id="srad" type="range" min={0.5} max={25} step={0.5} value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))} className="w-full" /></Field>
          </div>
          {!valid && (lon || lat) && <p role="alert" className="text-2xs text-red-300">Enter a longitude within +-180 and a latitude within +-85.</p>}
          {system && <p className="text-2xs text-slate-500">Area limit: {system.limits.max_aoi_km2.toLocaleString('en-US')} km2. This AOI: ~{(Math.PI * radiusKm ** 2).toFixed(1)} km2.</p>}
          </>)}
        </div>
        <div className="space-y-3">
          <h3 className="text-xs font-medium text-slate-200">2. Date ranges</h3>
          {(['before', 'after'] as const).map((k) => (
            <div key={k} className="grid grid-cols-2 gap-2">
              <Field label={`${k} - from`} htmlFor={`${k}s`}><input id={`${k}s`} type="date" value={win[k].start} onChange={(e) => setWin({ ...win, [k]: { ...win[k], start: e.target.value } })} className={inputCls} /></Field>
              <Field label={`${k} - to`} htmlFor={`${k}e`}><input id={`${k}e`} type="date" value={win[k].end} onChange={(e) => setWin({ ...win, [k]: { ...win[k], end: e.target.value } })} className={inputCls} /></Field>
            </div>
          ))}
          {!datesOk && <p role="alert" className="text-2xs text-red-300">Each range must be ordered, and the before range must end before the after range starts.</p>}
          <Field label={`Maximum cloud cover: ${cloud}%`} htmlFor="scloud" hint="Applied to the catalogue's cloud estimate. Cloud, shadow and cirrus pixels are also masked from the Sentinel-2 scene classification during processing."><input id="scloud" type="range" min={0} max={100} step={5} value={cloud} onChange={(e) => setCloud(Number(e.target.value))} className="w-full" /></Field>
          <Field label="Detection method" htmlFor="smethod" hint="At 10 m resolution the spectral baseline is recommended: the learned model was trained on 0.5-2 m imagery.">
            <select id="smethod" value={method} onChange={(e) => setMethod(e.target.value as DetectionMethod)} className={inputCls}>
              <option value="spectral_cva">Spectral baseline (recommended)</option><option value="ndvi_diff">NDVI difference (vegetation)</option><option value="auto">Automatic</option>
              {system?.ml.any_model_ready && <option value="learned_siamese">Learned model (experimental at 10 m)</option>}
            </select>
          </Field>
          <Button tone="accent" className="w-full py-2" disabled={!canSearch} loading={busy} onClick={search}><Search className="h-3.5 w-3.5" aria-hidden /> Search Sentinel-2 scenes</Button>
        </div>
      </section>

      {error && <p role="alert" className="rounded border border-red-500/30 bg-red-500/[0.07] px-3 py-2 text-xs text-red-300">{error}</p>}
      {busy && <div className="flex items-center gap-2 text-xs text-slate-400"><Spinner /> Querying the catalogue...</div>}

      {result && (
        <section className="space-y-3 rounded-lg border border-white/[0.08] bg-ink-850 p-4" aria-label="Search results">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="label">3. Choose scenes ({result.provider}, ~{result.aoi_area_km2.toFixed(1)} km2)</h3></div>
          {result.warnings.map((w) => <p key={w} className="flex gap-1.5 text-xs text-amber-200"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{w}</p>)}
          {(['before', 'after'] as const).map((k) => {
            const list = result[k]; const sel = k === 'before' ? selB : selA; const suggested = k === 'before' ? result.suggested_before : result.suggested_after
            return (
              <div key={k}>
                <h4 className="label mb-1">{k} window &middot; {list.length} scene{list.length === 1 ? '' : 's'}</h4>
                {list.length === 0 ? <p className="rounded border border-white/[0.07] px-3 py-2 text-xs text-slate-500">No scene. Widen the dates or raise the cloud limit; GeoTrace will not substitute an arbitrary scene.</p> : (
                  <ul className="max-h-52 overflow-y-auto rounded border border-white/[0.07]" role="radiogroup" aria-label={`${k} scene`}>
                    {list.map((s) => <SceneRow key={s.product_id} s={s} selected={sel === s.product_id} suggested={suggested === s.product_id} onSelect={() => (k === 'before' ? setSelB(s.product_id) : setSelA(s.product_id))} onPreview={() => void showPreview(s)} />)}
                  </ul>
                )}
              </div>
            )
          })}
          <details className="text-2xs text-slate-500"><summary className="cursor-pointer text-slate-400">Automatic selection rule</summary><p className="mt-1">{result.suggestion_rule}</p></details>
          {selB && selA && sel(result.before, selB) && sel(result.after, selA) && (
            <p className="text-xs text-slate-400">Interval: {formatDate(sel(result.before, selB)!.acquired_at)} &rarr; {formatDate(sel(result.after, selA)!.acquired_at)}. Cloud {formatPct((sel(result.before, selB)!.cloud_cover_pct ?? 0) / 100, 1)} / {formatPct((sel(result.after, selA)!.cloud_cover_pct ?? 0) / 100, 1)}.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button tone="accent" disabled={!canAcquire || !selB || !selA} loading={acquiring} onClick={() => acquire(false)} title={canAcquire ? undefined : 'Imagery retrieval is not configured'}>Retrieve selected scenes and run</Button>
            <Button disabled={!canAcquire || acquiring} onClick={() => acquire(true)}><Wand2 className="h-3.5 w-3.5" aria-hidden /> Use the automatic rule</Button>
          </div>
        </section>
      )}

      {preview && (
        <div role="dialog" aria-label="Scene preview" className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-6" onClick={() => setPreview(null)}>
          <div className="panel-solid max-h-full max-w-3xl overflow-auto rounded-lg p-3" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between text-xs text-slate-300"><span className="font-mono">{preview.label} (true colour, area centre)</span><button className="focus-ring rounded text-slate-500 hover:text-slate-100" aria-label="Close preview" onClick={() => setPreview(null)}><X className="h-4 w-4" /></button></div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preview.url} alt="Sentinel-2 true colour preview of the selected scene" className="max-h-[70vh] rounded" />
          </div>
        </div>
      )}
    </div>
  )
}

function bboxOf(g: unknown): [number, number, number, number] {
  const ring = ((g as { coordinates: number[][][] }).coordinates[0])
  const xs = ring.map((p) => p[0]), ys = ring.map((p) => p[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]
}
