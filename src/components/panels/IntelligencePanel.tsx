'use client'

import { useEffect, useState } from 'react'
import { BadgeCheck, Ban, Download, MapPin, Navigation, ShieldAlert, X } from 'lucide-react'
import { api, ApiError, authHeaders, API_BASE, type ChangeFeature } from '@/lib/api'
import { canWrite } from '@/lib/auth'
import { basisLabel, categoryLabel, cn, formatArea, formatCoord, formatDate, formatM2, formatPct, SEVERITY_COLOR } from '@/lib/format'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { Button, Chip, DemoBadge, EmptyBlock, ErrorBlock, Section, SeverityBadge, Skeleton, Stat } from '@/components/ui/kit'
import ExplainButton from '@/components/analytics/ExplainButton'

/** Authenticated image (the chip endpoint is access controlled so <img src> cannot be used directly). */
function Chip2({ analysisId, featureId, layer, label }: { analysisId: string; featureId: string; layer: 'before' | 'after'; label: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let alive = true
    let objectUrl: string | null = null
    setUrl(null); setFailed(false)
    fetch(`${API_BASE}/analyses/${analysisId}/features/${featureId}/chip/${layer}.png?size=360&pad=1.2`, { headers: authHeaders() })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob() })
      .then((b) => { if (alive) { objectUrl = URL.createObjectURL(b); setUrl(objectUrl) } })
      .catch(() => alive && setFailed(true))
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [analysisId, featureId, layer])
  return (
    <figure className="min-w-0 flex-1">
      <div className="relative aspect-square overflow-hidden rounded border border-[color:var(--line-strong)] bg-black/40">
        {/* authenticated blob URL: next/image cannot fetch it */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {url ? <img src={url} alt={`${label} imagery around the selected change`} className="h-full w-full object-cover" /> : failed ? <div className="flex h-full items-center justify-center p-2 text-center text-2xs text-slate-600">Evidence image unavailable</div> : <Skeleton className="h-full w-full" />}
        <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/50" />
      </div>
      <figcaption className="mt-1 text-center font-mono text-2xs uppercase tracking-wider text-slate-500">{label}</figcaption>
    </figure>
  )
}

export default function IntelligencePanel() {
  const analysis = useAppStore(selectActiveAnalysis)
  const selectedId = useAppStore((s) => s.selectedFeatureId)
  const selectFeature = useAppStore((s) => s.selectFeature)
  const setRight = useAppStore((s) => s.setRightPanelOpen)
  const requestFly = useAppStore((s) => s.requestFly)
  const bump = useAppStore((s) => s.bumpFeatures)
  const toast = useAppStore((s) => s.toast)
  const user = useAppStore((s) => s.authUser)
  const regions = useAppStore((s) => s.regions)
  const [feature, setFeature] = useState<ChangeFeature | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [incidents, setIncidents] = useState<{ id: string; title: string; status: string; severity: ChangeFeature['severity'] }[]>([])

  useEffect(() => {
    if (!analysis || !selectedId) { setFeature(null); setError(null); setIncidents([]); return }
    let alive = true
    setError(null)
    api.analyses.feature(analysis.id, selectedId).then((f) => alive && setFeature(f)).catch((e) => alive && setError(e instanceof ApiError ? e.message : 'Could not load detection'))
    api.alerts.incidents({ analysis_id: analysis.id, limit: 100 }).then((p) => alive && setIncidents(p.items.filter((i) => i.feature_id === selectedId))).catch(() => alive && setIncidents([]))
    return () => { alive = false }
  }, [analysis, selectedId])

  async function review(status: 'confirmed' | 'rejected' | 'unreviewed') {
    if (!analysis || !feature) return
    setBusy(true)
    try {
      setFeature(await api.analyses.review(analysis.id, feature.id, status))
      bump()
      toast('success', status === 'unreviewed' ? 'Review cleared' : `Marked ${status}`)
    } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Review failed') } finally { setBusy(false) }
  }

  const region = feature?.distance_to_boundary_m !== null && feature ? regions.find((r) => r) : null
  const det = analysis?.processing?.detection

  return (
    <aside aria-label="Selected change details" className="panel flex h-full w-[340px] shrink-0 flex-col border-y-0 border-r-0">
      <header className="hairline-b flex h-9 items-center justify-between px-3">
        <h2 className="label">Intelligence</h2>
        <button onClick={() => setRight(false)} aria-label="Collapse intelligence panel" className="focus-ring rounded text-slate-500 hover:text-slate-200"><X className="h-3.5 w-3.5" /></button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!analysis && <EmptyBlock title="No analysis selected" hint="Choose or run an analysis to inspect detected changes here." />}
        {analysis && !selectedId && (
          <EmptyBlock icon={<MapPin className="h-6 w-6" />} title="Select a detection" hint="Click a polygon on the globe or map, or pick one from the detection list below." />
        )}
        {error && <ErrorBlock message={error} />}
        {analysis && selectedId && !feature && !error && <div className="space-y-3 p-3"><Skeleton className="h-6 w-2/3" /><Skeleton className="h-28 w-full" /><Skeleton className="h-20 w-full" /></div>}
        {feature && analysis && (
          <>
            <div className="hairline-b px-3 py-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-medium text-slate-100">Change #{feature.seq}</div>
                  <div className="mt-0.5 text-xs text-slate-400">{categoryLabel(feature.category)}</div>
                </div>
                <div className="flex flex-col items-end gap-1"><SeverityBadge severity={feature.severity} />{analysis.is_demo && <DemoBadge />}</div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Stat label="Area (measured)" value={formatArea(feature.area_m2)} sub={formatM2(feature.area_m2)} />
                <Stat label="Perimeter" value={`${Math.round(feature.perimeter_m).toLocaleString('en-US')} m`} />
                <Stat label="Magnitude" value={feature.magnitude.toFixed(2)} sub={det?.magnitude_kind?.replace(/_/g, ' ')} />
                <Stat label={feature.confidence !== null ? 'Model score' : 'Confidence'} value={feature.confidence !== null ? formatPct(feature.confidence, 0) : 'n/a'} sub={feature.confidence !== null ? 'uncalibrated' : 'not meaningful for this method'} />
              </div>
            </div>

            <Section title="Before / after evidence">
              <div className="flex gap-2">
                <Chip2 analysisId={analysis.id} featureId={feature.id} layer="before" label={`Before ${formatDate(analysis.before_date)}`} />
                <Chip2 analysisId={analysis.id} featureId={feature.id} layer="after" label={`After ${formatDate(analysis.after_date)}`} />
              </div>
            </Section>

            <Section title="Interpretation">
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between gap-3"><dt className="text-slate-500">Basis</dt><dd className="text-right text-slate-300">{basisLabel(feature.category_basis)}</dd></div>
                {feature.delta_ndvi !== null && <div className="flex justify-between gap-3"><dt className="text-slate-500">Mean dNDVI</dt><dd className="font-mono text-slate-300">{feature.delta_ndvi.toFixed(2)}</dd></div>}
                <div className="flex justify-between gap-3"><dt className="text-slate-500">Method</dt><dd className="text-right text-slate-300">{analysis.method?.replace(/_/g, ' ') ?? '-'}</dd></div>
              </dl>
              <p className="mt-2 rounded border border-amber-400/15 bg-amber-400/[0.04] p-2 text-2xs leading-relaxed text-amber-200/80">
                An observed image difference, not proof of construction, damage or illegal activity. Category and severity are heuristic; verify against source imagery.
              </p>
              <ul className="mt-2 space-y-0.5 text-2xs text-slate-500">{feature.severity_reasons.map((r) => <li key={r} className="flex gap-1.5"><span style={{ color: SEVERITY_COLOR[feature.severity] }}>&bull;</span>{r}</li>)}</ul>
            </Section>

            <Section title="Location">
              <div className="flex items-center justify-between gap-2">
                <div className="font-mono text-xs text-slate-300">{formatCoord(feature.centroid[0], feature.centroid[1])}</div>
                <Button tone="ghost" onClick={() => requestFly({ bbox: feature.bbox })}><Navigation className="h-3.5 w-3.5" aria-hidden /> Fly to</Button>
              </div>
              {feature.distance_to_boundary_m !== null && <p className="mt-1.5 text-2xs text-slate-500">Nearest monitored boundary: <span className="font-mono text-slate-300">{Math.round(feature.distance_to_boundary_m).toLocaleString('en-US')} m</span>{region ? '' : ''}</p>}
            </Section>

            <Section title="Related alerts">
              {incidents.length ? <ul className="space-y-1">{incidents.map((i) => <li key={i.id} className="flex items-center gap-2 text-xs text-slate-300"><ShieldAlert className="h-3.5 w-3.5 text-amber-300" aria-hidden /><span className="min-w-0 flex-1 truncate">{i.title}</span><Chip>{i.status}</Chip></li>)}</ul> : <p className="text-2xs text-slate-600">No alert rule matched this detection.</p>}
            </Section>

            <Section title="Verification">
              <div className="flex items-center gap-2">
                <Chip tone={feature.review_status === 'confirmed' ? 'ok' : feature.review_status === 'rejected' ? 'danger' : 'default'}>{feature.review_status}</Chip>
                {feature.review_note && <span className="truncate text-2xs text-slate-500">{feature.review_note}</span>}
              </div>
              {canWrite(user?.role) ? (
                <div className="mt-2 flex gap-1.5">
                  <Button tone="accent" disabled={busy} onClick={() => review('confirmed')}><BadgeCheck className="h-3.5 w-3.5" aria-hidden /> Confirm</Button>
                  <Button tone="danger" disabled={busy} onClick={() => review('rejected')}><Ban className="h-3.5 w-3.5" aria-hidden /> Reject</Button>
                  {feature.review_status !== 'unreviewed' && <Button tone="ghost" disabled={busy} onClick={() => review('unreviewed')}>Clear</Button>}
                </div>
              ) : <p className="mt-2 text-2xs text-slate-600">Viewers cannot change review status.</p>}
            </Section>

            <Section title="Analyse and export">
              <div className="flex flex-wrap gap-1.5">
                <ExplainButton analysisId={analysis.id} featureId={feature.id} />
                <Button onClick={() => void api.analyses.export(analysis.id, 'geojson', { ids: [feature.id] }).then((r) => toast('success', `Exported ${r.featureCount ?? 1} feature (GeoJSON)`)).catch((e) => toast('error', e.message))}><Download className="h-3.5 w-3.5" aria-hidden /> GeoJSON</Button>
                <Button onClick={() => void api.analyses.export(analysis.id, 'gpkg', { ids: [feature.id] }).then(() => toast('success', 'Exported GeoPackage')).catch((e) => toast('error', e.message))}><Download className="h-3.5 w-3.5" aria-hidden /> GPKG</Button>
              </div>
            </Section>
          </>
        )}
      </div>
      {feature && <button className={cn('hairline-t focus-ring py-2 text-center text-2xs text-slate-500 hover:text-slate-200')} onClick={() => selectFeature(null)}>Clear selection</button>}
    </aside>
  )
}
