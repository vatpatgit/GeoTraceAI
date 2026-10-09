'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { Activity, Flame, MapPin, RefreshCw, Waves } from 'lucide-react'
import { api, ApiError, type HazardAlert, type HazardKind, type HazardRefresh, type HazardSeverity } from '@/lib/api'
import { HAZARD_LABEL } from '@/lib/api/hazards'
import { formatRelative } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, EmptyBlock, ErrorBlock, Segmented, Skeleton } from '@/components/ui/kit'
import { Card } from './PageFrame'

const ICON: Record<HazardKind, React.ComponentType<{ className?: string }>> = { earthquake: Activity, fire: Flame, storm: Waves }
const TONE: Record<HazardSeverity, 'default' | 'warn' | 'danger'> = { low: 'default', medium: 'warn', high: 'danger', critical: 'danger' }
const num = (v: unknown, d = 1) => (typeof v === 'number' ? v.toFixed(d) : null)

function Facts({ a }: { a: HazardAlert }) {
  const d = a.details
  const rows: [string, string | null][] = a.kind === 'earthquake'
    ? [['Magnitude', num(d.magnitude)], ['Depth', num(d.depth_km, 0) ? `${num(d.depth_km, 0)} km` : null], ['Tsunami flag', d.tsunami_flag ? 'set by USGS' : 'not set']]
    : a.kind === 'fire'
      ? [['Hotspots', String(d.hotspots ?? '')], ['Max radiative power', num(d.max_frp_mw) ? `${num(d.max_frp_mw)} MW` : null], ['Basis', 'satellite thermal anomalies, not confirmed fires']]
      : [['Category', typeof d.category === 'string' ? d.category : null], ['Provider', typeof d.provider === 'string' ? d.provider : null]]
  return (
    <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-2xs text-slate-400">
      {rows.filter(([, v]) => v).map(([k, v]) => <div key={k} className="flex gap-1"><dt>{k}:</dt><dd className="text-slate-200">{v}</dd></div>)}
      {typeof d.source_url === 'string' && <a className="text-accent underline" href={d.source_url} target="_blank" rel="noopener noreferrer">source</a>}
      {typeof d.url === 'string' && <a className="text-accent underline" href={d.url} target="_blank" rel="noopener noreferrer">USGS event page</a>}
    </dl>
  )
}

export default function HazardAlertsSection() {
  const router = useRouter()
  const requestFly = useAppStore((s) => s.requestFly)
  const [items, setItems] = useState<HazardAlert[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [kind, setKind] = useState<'all' | HazardKind>('all')
  const [last, setLast] = useState<HazardRefresh | null>(null)

  const load = useCallback(async () => {
    try { setItems(await api.hazards.list({ kind: kind === 'all' ? undefined : kind })); setError(null) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load hazard alerts.') }
  }, [kind])
  useEffect(() => { void load() }, [load])

  async function refresh() {
    setBusy(true)
    try { setLast(await api.hazards.refresh({ force: true })); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not refresh the hazard feed.') }
    finally { setBusy(false) }
  }
  async function markAll() { await api.hazards.markRead({ all: true }).catch(() => undefined); await load() }
  const unread = (items ?? []).filter((a) => !a.read_at).length

  return (
    <Card title="Live hazard alerts near your areas" action={
      <div className="flex items-center gap-2">
        <Segmented label="Hazard type" size="sm" value={kind} onChange={setKind} options={[{ value: 'all', label: 'All' }, { value: 'earthquake', label: 'Quakes' }, { value: 'fire', label: 'Fires' }, { value: 'storm', label: 'Storms' }]} />
        {unread > 0 && <Button tone="ghost" onClick={() => void markAll()}>Mark {unread} read</Button>}
        <Button tone="accent" loading={busy} onClick={() => void refresh()}><RefreshCw className="h-3.5 w-3.5" aria-hidden /> Check now</Button>
      </div>
    }>
      <p className="mb-2 px-3 pt-2 text-2xs text-slate-500">
        Earthquakes (USGS), fire hotspots (NASA FIRMS) and storm events (NASA EONET) from a live feed, matched to your saved areas by distance. They are third-party observations, separate from
        satellite change detections, and proximity does not mean impact.
      </p>
      {error && <ErrorBlock message={error} onRetry={() => void load()} />}
      {last && Object.keys(last.errors).length > 0 && (
        <p role="alert" className="mx-3 mb-2 rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-2xs text-amber-200">
          Some feeds could not be read, so their status is unknown (not “no alerts”): {Object.entries(last.errors).map(([k, v]) => `${k}: ${v}`).join('; ')}
        </p>
      )}
      {items === null && !error ? <div className="space-y-2 p-3"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
        : items && items.length === 0 ? <EmptyBlock title="No active hazard alerts near your areas" hint={last ? `Checked ${formatRelative(last.checked_at)}: ${Object.entries(last.fetched).map(([k, v]) => `${v} ${k} records`).join(', ')} reviewed.` : 'Use “Check now” to query the live feed.'} />
        : (
          <ul>
            {(items ?? []).map((a) => {
              const Icon = ICON[a.kind]
              return (
                <li key={a.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-[color:var(--line)] px-3 py-2.5 last:border-0">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Chip tone={TONE[a.severity]}>{a.severity}</Chip>
                      <Icon className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                      <span className="text-xs font-medium text-slate-100">{a.title}</span>
                      {!a.read_at && <Chip tone="accent">new</Chip>}
                    </div>
                    <div className="mt-0.5 text-2xs text-slate-500">
                      {HAZARD_LABEL[a.kind]} · {a.aoi_name ?? 'area'} · {a.distance_km === 0 ? 'inside the area' : `${a.distance_km.toFixed(0)} km from the area`} · {a.occurred_at ? formatRelative(a.occurred_at) : 'time not provided'}
                    </div>
                    <Facts a={a} />
                  </div>
                  <Button tone="ghost" onClick={() => { requestFly({ center: [a.lon, a.lat], zoom: a.kind === 'storm' ? 6 : 9 }); router.push('/map') }} aria-label={`Show ${a.title} on the map`}>
                    <MapPin className="h-3.5 w-3.5" aria-hidden /> Show on map
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
    </Card>
  )
}

