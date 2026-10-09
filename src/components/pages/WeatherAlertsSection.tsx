'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertOctagon, AlertTriangle, CloudLightning, Info, MapPin, RefreshCw, ShieldAlert } from 'lucide-react'
import { api, ApiError, type Aoi, type AoiWeatherState, type WeatherAlert, type WeatherEvent, type WeatherSeverity } from '@/lib/api'
import { canWrite } from '@/lib/auth'
import { cn, formatRelative } from '@/lib/format'
import { alertWindow, TAG_LABEL, WEATHER_COLOR, WEATHER_RANK } from '@/lib/weather'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, EmptyBlock, ErrorBlock, Field, inputCls, Skeleton, Switch } from '@/components/ui/kit'
import { Card } from './PageFrame'

const ICON: Record<WeatherSeverity, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  unknown: Info, minor: Info, moderate: AlertTriangle, severe: ShieldAlert, extreme: AlertOctagon,
}

/** Severity is conveyed by word + icon shape + colour (never colour alone). */
export function SeverityTag({ severity }: { severity: WeatherSeverity }) {
  const Icon = ICON[severity]
  return (
    <span className="inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider" style={{ color: WEATHER_COLOR[severity] }} aria-label={`Severity: ${severity}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden /> {severity}
    </span>
  )
}

export function WeatherAlertDetails({ a }: { a: WeatherAlert }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-2xs text-slate-400">
      <dt>Source</dt><dd className="text-slate-200">{a.source ?? 'not provided'} · OpenWeather</dd>
      <dt>Certainty</dt><dd className="text-slate-200">{a.certainty}</dd>
      <dt>Urgency</dt><dd className="text-slate-200">{a.urgency}</dd>
      <dt>Event time</dt><dd className="text-slate-200">{alertWindow(a)}</dd>
      <dt>Affected area</dt><dd className="text-slate-200">{a.geometry ? `${a.geometry.type} supplied by the provider (indicative, not the extent of damage)` : 'no geometry supplied'}</dd>
      <dt>AOI</dt><dd className="text-slate-200">{a.aoi_name ?? '-'}</dd>
      <dt>Provider ID</dt><dd className="break-all font-mono text-slate-300">{a.source_alert_id}</dd>
      <dt>Last checked</dt><dd className="text-slate-200">{formatRelative(a.last_checked_at)}{a.change_count > 0 ? ` · updated ${a.change_count}×` : ''}</dd>
    </dl>
  )
}

function AlertRow({ a, selected, onShow }: { a: WeatherAlert; selected: boolean; onShow: () => void }) {
  return (
    <li className={cn('border-b border-[color:var(--line)] px-3 py-3 last:border-0', selected && 'bg-accent/[0.05]')} style={{ borderLeft: `3px solid ${WEATHER_COLOR[a.severity]}` }}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityTag severity={a.severity} />
            <span className="text-xs font-medium text-slate-100">{a.title}</span>
            {a.tags.map((t) => <Chip key={t}>{TAG_LABEL(t)}</Chip>)}
          </div>
          {a.description ? <p className="mt-1 text-xs2 text-slate-400">{a.description}</p> : <p className="mt-1 text-xs2 text-slate-600">No description provided.</p>}
        </div>
        <Button tone="ghost" onClick={onShow} disabled={!a.geometry} title={a.geometry ? undefined : 'The provider supplied no geometry for this alert'} aria-label={`Show ${a.title} on the map`}>
          <MapPin className="h-3.5 w-3.5" aria-hidden /> Map
        </Button>
      </div>
      <div className="mt-2"><WeatherAlertDetails a={a} /></div>
    </li>
  )
}

export default function WeatherAlertsSection() {
  const router = useRouter()
  const user = useAppStore((s) => s.authUser)
  const projects = useAppStore((s) => s.projects)
  const projectId = useAppStore((s) => s.activeProjectId)
  const regions = useAppStore((s) => s.regions)
  const selectedId = useAppStore((s) => s.selectedWeatherId)
  const setAlerts = useAppStore((s) => s.setWeatherAlerts)
  const selectWeather = useAppStore((s) => s.selectWeather)
  const toast = useAppStore((s) => s.toast)
  const writable = canWrite(user?.role)

  const [aois, setAois] = useState<Aoi[]>([])
  const [aoiId, setAoiId] = useState('')
  const [states, setStates] = useState<AoiWeatherState[]>([])
  const [items, setItems] = useState<WeatherAlert[]>([])
  const [events, setEvents] = useState<WeatherEvent[]>([])
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, ev, a] = await Promise.all([api.weather.list(), api.weather.events(true), projectId ? api.projects.aois(projectId) : Promise.resolve([] as Aoi[])])
      setConfigured(list.configured); setItems(list.items); setStates(list.aois); setEvents(ev); setAois(a)
      setAlerts(list.items)
      setAoiId((cur) => cur || a[0]?.id || '')
      setError(null)
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load weather alerts.') } finally { setLoading(false) }
  }, [projectId, setAlerts])
  useEffect(() => { void load() }, [load])

  const state = states.find((s) => s.aoi_id === aoiId) ?? null
  const shown = useMemo(() => items.filter((a) => a.status === 'active' && (!aoiId || a.aoi_id === aoiId)).sort((x, y) => WEATHER_RANK[y.severity] - WEATHER_RANK[x.severity]), [items, aoiId])

  async function addRegionAoi(regionId: string) {
    if (!projectId || !regionId) return
    const r = regions.find((x) => x.id === regionId)
    try {
      const aoi = await api.projects.createAoi(projectId, { name: r?.name ?? 'Region', source: 'region', region_id: regionId })
      setAois((p) => [...p, aoi]); setAoiId(aoi.id)
    } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Could not create the AOI from this region.') }
  }

  async function refresh(force: boolean) {
    if (!aoiId) return
    setBusy(true); setNote(null); setError(null)
    try {
      const r = await api.weather.refresh({ aoi_id: aoiId, force })
      setNote(r.cached ? 'Showing the stored result (checked recently); use Force refresh to ask the provider again.'
        : `${r.new} new · ${r.updated} updated · ${r.unchanged} unchanged · ${r.expired} ended`)
      await load()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Refresh failed.'
      await load().catch(() => undefined) // refresh the attempt timestamp / stored alerts, then show the failure
      setError(msg)
    } finally { setBusy(false) }
  }

  async function toggleMonitoring(on: boolean) {
    try { await api.weather.setMonitoring(aoiId, on); await load() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Could not change monitoring.') }
  }

  async function markRead() {
    try { await api.weather.markRead({ all: true }); setEvents([]) } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Could not mark as read.') }
  }

  function show(a: WeatherAlert) {
    selectWeather(a.id, { fly: true })
    router.push('/map')
  }

  return (
    <Card title="Weather alerts (OpenWeather)" action={<CloudLightning className="h-4 w-4 text-slate-500" aria-hidden />}>
      <p className="mb-3 max-w-3xl text-2xs text-slate-500">
        Official and model-generated weather alerts that intersect a saved area of interest. They are third-party forecasts and warnings, shown as provided: not satellite observations and not a measurement of damage.
        {configured === false && ' The server has no OpenWeather API key configured (OPENWEATHER_API_KEY).'}
      </p>

      {events.length > 0 && (
        <div role="status" className="mb-3 flex items-center justify-between gap-3 rounded-md border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-100">
          <span>{events.length} new or updated alert{events.length === 1 ? '' : 's'} since you last looked: {events.slice(0, 3).map((e) => `${e.kind === 'new' ? 'New' : 'Updated'}: ${e.title}`).join(' · ')}{events.length > 3 ? ' …' : ''}</span>
          <Button tone="ghost" onClick={() => void markRead()}>Mark read</Button>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Field label="Area of interest" htmlFor="wx-aoi">
            <select id="wx-aoi" className={inputCls} value={aoiId} onChange={(e) => setAoiId(e.target.value)} disabled={aois.length === 0}>
              {aois.length === 0 && <option value="">No AOIs in this project</option>}
              {aois.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.area_km2.toFixed(0)} km²)</option>)}
            </select>
          </Field>
        </div>
        {writable && projectId && regions.length > 0 && (
          <div className="w-56">
            <Field label="Add AOI from a monitored region" htmlFor="wx-region">
              <select id="wx-region" className={inputCls} value="" onChange={(e) => void addRegionAoi(e.target.value)}>
                <option value="">Choose a region…</option>
                {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </Field>
          </div>
        )}
        {writable && <Button tone="accent" loading={busy} disabled={!aoiId || configured === false} onClick={() => void refresh(false)}><RefreshCw className="h-3.5 w-3.5" aria-hidden /> Get alerts</Button>}
        {writable && <Button tone="ghost" loading={busy} disabled={!aoiId || configured === false} onClick={() => void refresh(true)} title="Ask the provider again even if checked recently">Force refresh</Button>}
        {writable && aoiId && (
          <label className="flex items-center gap-2 pb-1.5 text-2xs text-slate-400" title="Included in scheduled refreshes when the server has WEATHER_REFRESH_MINUTES enabled">
            <Switch checked={state?.monitoring ?? false} onChange={(v) => void toggleMonitoring(v)} label="Monitor this AOI for weather alerts" /> Monitor
          </label>
        )}
      </div>

      <div className="mb-2 text-2xs text-slate-500" aria-live="polite">
        {state?.last_checked_at ? `Last retrieved ${formatRelative(state.last_checked_at)}${state.last_status === 'error' ? ' (that attempt failed)' : ''}` : aoiId ? 'Not retrieved yet for this AOI.' : ''}
        {note && <span className="ml-2 text-slate-300">{note}</span>}
      </div>

      {error && <ErrorBlock title="Weather alerts" message={error} onRetry={() => void (aoiId ? refresh(false) : load())} />}
      {!error && state?.last_status === 'error' && state.last_error && <p role="alert" className="mb-2 text-2xs text-red-300">Last refresh failed: {state.last_error}</p>}

      <div className="-mx-3 -mb-3 border-t border-[color:var(--line)]">
        {loading && items.length === 0 ? <div className="space-y-2 p-3"><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
          : shown.length === 0 ? (
            <EmptyBlock title={state?.last_checked_at ? 'No active weather alerts for this area' : 'No alerts retrieved yet'}
              hint={state?.last_checked_at && state.last_status === 'ok' ? `OpenWeather returned no alerts for this AOI at ${formatRelative(state.last_checked_at)}. That is a valid answer, not an error.` : 'Choose an AOI and select “Get alerts” to ask OpenWeather.'} />
          ) : <ul aria-label="Weather alerts">{shown.map((a) => <AlertRow key={a.id} a={a} selected={a.id === selectedId} onShow={() => show(a)} />)}</ul>}
      </div>
      {projects.length === 0 && !loading && <p className="mt-2 text-2xs text-slate-500">Create a project and AOI first.</p>}
    </Card>
  )
}
