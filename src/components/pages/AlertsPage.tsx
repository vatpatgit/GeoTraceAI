'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, MapPin, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, ApiError, SEVERITIES, type AlertRule, type AlertRuleInput, type Incident, type IncidentStatus, type Severity } from '@/lib/api'
import { canWrite } from '@/lib/auth'
import { useAsync } from '@/hooks/useAsync'
import { categoryLabel, cn, formatArea, formatDate, formatRelative } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, DemoBadge, EmptyBlock, ErrorBlock, Field, inputCls, Segmented, SeverityBadge, Skeleton, Switch } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'
import WeatherAlertsSection from './WeatherAlertsSection'

const STATUS_TONE: Record<IncidentStatus, 'danger' | 'warn' | 'ok'> = { open: 'danger', acknowledged: 'warn', resolved: 'ok' }
const CATEGORIES = ['vegetation_decrease', 'vegetation_increase', 'vegetation_change', 'building_change', 'land_cover_change', 'unclassified_change']

const BLANK: AlertRuleInput = { name: '', enabled: true, region_id: null, region_relation: 'intersects', distance_m: null, categories: null, min_area_m2: 0, min_severity: 'low', min_magnitude: null, min_confidence: null, dedup_mode: 'spatial', dedup_window_days: 30, dedup_overlap: 0.5 }

function IncidentRow({ inc, onChange, writable }: { inc: Incident; onChange: () => void; writable: boolean }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const toast = useAppStore((s) => s.toast)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const selectFeature = useAppStore((s) => s.selectFeature)
  const requestFly = useAppStore((s) => s.requestFly)

  async function setStatus(status: IncidentStatus) {
    let note: string | undefined
    if (status === 'resolved') { const n = window.prompt('Resolution note (optional):'); if (n === null) return; note = n || undefined }
    setBusy(true)
    try { await api.alerts.setStatus(inc.id, status, note); onChange() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Update failed') } finally { setBusy(false) }
  }
  function show() {
    setActive(inc.analysis_id)
    if (inc.bbox) requestFly({ bbox: inc.bbox })
    selectFeature(inc.feature_id, { fly: true, center: inc.centroid ?? undefined, bbox: inc.bbox ?? undefined })
    router.push('/map')
  }

  return (
    <li className="border-b border-white/[0.05] last:border-0">
      <div className="flex items-start gap-2 px-3 py-2.5">
        <button aria-label={open ? 'Hide evidence' : 'Show evidence'} aria-expanded={open} onClick={() => setOpen(!open)} className="focus-ring mt-0.5 text-slate-500 hover:text-slate-200">{open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={inc.severity} />
            <span className="text-xs font-medium text-slate-100">{inc.title}</span>
            <Chip tone={STATUS_TONE[inc.status]}>{inc.status}</Chip>
            {inc.is_demo && <DemoBadge />}
          </div>
          <p className="mt-0.5 text-xs2 text-slate-400">{inc.message}</p>
          <p className="mt-0.5 text-2xs text-slate-500">Rule “{inc.rule_name}” · {inc.analysis_name ?? 'analysis'} · {categoryLabel(inc.category)} · {inc.area_m2 != null ? formatArea(inc.area_m2) : '-'} · detected {formatRelative(inc.detected_at)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button tone="ghost" onClick={show} aria-label={`Show ${inc.title} on the map`}><MapPin className="h-3.5 w-3.5" aria-hidden /> Map</Button>
          {writable && inc.status === 'open' && <Button tone="default" loading={busy} onClick={() => void setStatus('acknowledged')}>Acknowledge</Button>}
          {writable && inc.status !== 'resolved' && <Button tone="accent" loading={busy} onClick={() => void setStatus('resolved')}><Check className="h-3.5 w-3.5" aria-hidden /> Resolve</Button>}
          {writable && inc.status === 'resolved' && <Button tone="ghost" loading={busy} onClick={() => void setStatus('open')}>Reopen</Button>}
        </div>
      </div>
      {open && (
        <div className="mx-3 mb-3 ml-8 space-y-2 rounded-md border border-white/[0.06] bg-black/20 p-3 text-2xs text-slate-400">
          <p className="text-slate-300">Why this alert fired (stored evidence — values at evaluation time):</p>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed">{JSON.stringify({ matched: inc.evidence.matched, rule: inc.evidence.rule }, null, 2)}</pre>
          {inc.evidence.notice && <p className="text-amber-200/80">{inc.evidence.notice}</p>}
          {inc.resolution_note && <p>Resolution note: {inc.resolution_note}</p>}
          <p>Detected {formatDate(inc.detected_at, { time: true })}{inc.acknowledged_at && ` · acknowledged ${formatDate(inc.acknowledged_at, { time: true })}`}{inc.resolved_at && ` · resolved ${formatDate(inc.resolved_at, { time: true })}`}</p>
        </div>
      )}
    </li>
  )
}

function RuleEditor({ initial, onSaved, onCancel }: { initial: AlertRule | null; onSaved: () => void; onCancel: () => void }) {
  const regions = useAppStore((s) => s.regions)
  const toast = useAppStore((s) => s.toast)
  const [f, setF] = useState<AlertRuleInput>(initial ? { ...BLANK, ...initial } : BLANK)
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof AlertRuleInput>(k: K, v: AlertRuleInput[K]) => setF((p) => ({ ...p, [k]: v }))
  const needsDistance = f.region_relation === 'within_distance'
  const err = !f.name.trim() ? 'Name is required.' : needsDistance && !f.region_id ? 'Pick a region to measure the distance from.' : needsDistance && !(f.distance_m && f.distance_m > 0) ? 'Enter a distance in metres.' : null

  async function save() {
    if (err) return
    setBusy(true)
    try {
      const body: AlertRuleInput = { ...f, name: f.name.trim(), distance_m: needsDistance ? f.distance_m : null, categories: f.categories?.length ? f.categories : null }
      if (initial) await api.alerts.updateRule(initial.id, body); else await api.alerts.createRule(body)
      toast('success', initial ? 'Rule updated' : 'Rule created')
      onSaved()
    } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Could not save the rule') } finally { setBusy(false) }
  }
  const numOrNull = (v: string) => (v.trim() === '' ? null : Number(v))

  return (
    <Card title={initial ? `Edit rule: ${initial.name}` : 'New alert rule'}>
      <form className="grid gap-3 md:grid-cols-3" onSubmit={(e) => { e.preventDefault(); void save() }}>
        <div className="md:col-span-3"><Field label="Name" htmlFor="ar-name"><input id="ar-name" className={inputCls} maxLength={120} value={f.name} onChange={(e) => set('name', e.target.value)} /></Field></div>
        <Field label="Scope: monitored region" htmlFor="ar-region" hint="Leave empty to match anywhere.">
          <select id="ar-region" className={inputCls} value={f.region_id ?? ''} onChange={(e) => set('region_id', e.target.value || null)}>
            <option value="">Anywhere</option>{regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        <Field label="Relation to region" htmlFor="ar-rel">
          <select id="ar-rel" className={inputCls} value={f.region_relation} disabled={!f.region_id} onChange={(e) => set('region_relation', e.target.value as AlertRule['region_relation'])}>
            <option value="intersects">Intersects the region</option><option value="within_distance">Within distance of the region</option>
          </select>
        </Field>
        <Field label="Distance (m)" htmlFor="ar-dist"><input id="ar-dist" inputMode="decimal" className={inputCls} disabled={!needsDistance} value={f.distance_m ?? ''} onChange={(e) => set('distance_m', numOrNull(e.target.value))} /></Field>
        <Field label="Minimum area (m²)" htmlFor="ar-area"><input id="ar-area" inputMode="decimal" className={inputCls} value={f.min_area_m2 ?? 0} onChange={(e) => set('min_area_m2', Number(e.target.value) || 0)} /></Field>
        <Field label="Minimum severity (heuristic)" htmlFor="ar-sev">
          <select id="ar-sev" className={inputCls} value={f.min_severity} onChange={(e) => set('min_severity', e.target.value as Severity)}>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}</select>
        </Field>
        <Field label="Minimum magnitude (0–1)" htmlFor="ar-mag" hint="Optional"><input id="ar-mag" inputMode="decimal" className={inputCls} value={f.min_magnitude ?? ''} onChange={(e) => set('min_magnitude', numOrNull(e.target.value))} /></Field>
        <Field label="Minimum model score (0–1)" htmlFor="ar-conf" hint="Uncalibrated; ignored by detectors without a score."><input id="ar-conf" inputMode="decimal" className={inputCls} value={f.min_confidence ?? ''} onChange={(e) => set('min_confidence', numOrNull(e.target.value))} /></Field>
        <div className="md:col-span-3">
          <span className="label block">Categories (none selected = all)</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {CATEGORIES.map((c) => {
              const on = f.categories?.includes(c) ?? false
              return <button type="button" key={c} aria-pressed={on} onClick={() => set('categories', on ? (f.categories ?? []).filter((x) => x !== c) : [...(f.categories ?? []), c])} className={cn('focus-ring rounded border px-2 py-0.5 text-2xs', on ? 'border-accent/40 bg-accent/10 text-accent' : 'border-white/10 text-slate-400 hover:text-slate-200')}>{categoryLabel(c)}</button>
            })}
          </div>
        </div>
        <Field label="De-duplication">
          <Segmented label="De-duplication" size="sm" value={f.dedup_mode ?? 'spatial'} onChange={(v) => set('dedup_mode', v)} options={[{ value: 'spatial', label: 'Spatial', title: 'Suppress re-alerts for the same place within the window' }, { value: 'none', label: 'Off' }]} />
        </Field>
        <Field label="Window (days)" htmlFor="ar-win"><input id="ar-win" inputMode="numeric" className={inputCls} disabled={f.dedup_mode === 'none'} value={f.dedup_window_days ?? 30} onChange={(e) => set('dedup_window_days', Math.max(1, Number(e.target.value) || 1))} /></Field>
        <Field label="Overlap to count as same (0–1)" htmlFor="ar-ov"><input id="ar-ov" inputMode="decimal" className={inputCls} disabled={f.dedup_mode === 'none'} value={f.dedup_overlap ?? 0.5} onChange={(e) => set('dedup_overlap', Math.min(1, Math.max(0.01, Number(e.target.value) || 0.5)))} /></Field>
        <div className="flex items-center gap-3 md:col-span-3">
          <Button type="submit" tone="accent" loading={busy} disabled={!!err}>{initial ? 'Save rule' : 'Create rule'}</Button>
          <Button type="button" tone="ghost" onClick={onCancel}>Cancel</Button>
          {err && <span className="text-2xs text-amber-300">{err}</span>}
        </div>
      </form>
    </Card>
  )
}

export default function AlertsPage() {
  const user = useAppStore((s) => s.authUser)
  const regions = useAppStore((s) => s.regions)
  const toast = useAppStore((s) => s.toast)
  const writable = canWrite(user?.role)
  const [status, setStatus] = useState<'all' | IncidentStatus>('open')
  const [severity, setSeverity] = useState<Severity[]>([])
  const [editing, setEditing] = useState<AlertRule | 'new' | null>(null)
  const [page, setPage] = useState(0)
  const PAGE = 25

  const inc = useAsync(() => api.alerts.incidents({ status: status === 'all' ? undefined : [status], severity: severity.length ? severity : undefined, limit: PAGE, offset: page * PAGE }), [status, severity.join(','), page])
  const rules = useAsync(() => api.alerts.rules(), [])
  const stats = useAsync(() => api.alerts.stats(), [])
  const refresh = () => { inc.reload(); stats.reload(); rules.reload() }

  async function toggle(r: AlertRule) { try { await api.alerts.updateRule(r.id, { enabled: !r.enabled }); rules.reload() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Update failed') } }
  async function del(r: AlertRule) {
    if (!window.confirm(`Delete rule "${r.name}"? Its incidents are removed too.`)) return
    try { await api.alerts.deleteRule(r.id); refresh() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Delete failed') }
  }
  const scope = (r: AlertRule) => {
    const name = regions.find((x) => x.id === r.region_id)?.name
    return name ? `${r.region_relation === 'within_distance' ? `within ${r.distance_m} m of` : 'intersects'} ${name}` : 'anywhere'
  }

  return (
    <PageFrame wide title="Alert centre" subtitle="Alerts are raised when a stored detection satisfies a rule. Each detection raises at most one incident per rule; severity is a heuristic tier, not a probability.">
      <div className="grid grid-cols-3 gap-3 text-xs md:grid-cols-6">
        {(['open', 'acknowledged', 'resolved'] as const).map((s) => <div key={s} className="rounded-md border border-white/[0.07] bg-ink-900/60 p-2.5"><div className="label">{s}</div><div className="mt-0.5 font-mono text-lg text-slate-100">{stats.data?.by_status[s] ?? (stats.loading ? '…' : 0)}</div></div>)}
        {SEVERITIES.slice().reverse().slice(0, 3).map((s) => <div key={s} className="rounded-md border border-white/[0.07] bg-ink-900/60 p-2.5"><div className="label">unresolved {s}</div><div className="mt-0.5 font-mono text-lg text-slate-100">{stats.data?.unresolved_by_severity[s] ?? (stats.loading ? '…' : 0)}</div></div>)}
      </div>

      <Card title="Incidents" action={
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Status filter" size="sm" value={status} onChange={(v) => { setStatus(v); setPage(0) }} options={[{ value: 'open', label: 'Open' }, { value: 'acknowledged', label: 'Ack' }, { value: 'resolved', label: 'Resolved' }, { value: 'all', label: 'All' }]} />
          <div className="flex gap-1" role="group" aria-label="Severity filter">
            {SEVERITIES.map((s) => <button key={s} aria-pressed={severity.includes(s)} onClick={() => { setSeverity(severity.includes(s) ? severity.filter((x) => x !== s) : [...severity, s]); setPage(0) }} className={cn('focus-ring rounded border px-1.5 py-0.5 font-mono text-2xs uppercase', severity.includes(s) ? 'border-accent/40 bg-accent/10 text-accent' : 'border-white/10 text-slate-500 hover:text-slate-200')}>{s}</button>)}
          </div>
        </div>}>
        <div className="-m-3">
          {inc.error && <ErrorBlock message={inc.error} onRetry={inc.reload} />}
          {inc.loading && !inc.data && <div className="space-y-2 p-3"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>}
          {inc.data && inc.data.items.length === 0 && <EmptyBlock title="No incidents match" hint={rules.data?.length ? 'Alerts appear when a completed analysis contains detections that satisfy a rule.' : 'Create a rule below; new analyses are evaluated against enabled rules automatically.'} />}
          {inc.data && inc.data.items.length > 0 && <ul>{inc.data.items.map((i) => <IncidentRow key={i.id} inc={i} writable={writable} onChange={refresh} />)}</ul>}
          {inc.data && inc.data.total > PAGE && (
            <div className="flex items-center justify-between border-t border-white/[0.06] px-3 py-2 text-2xs text-slate-500">
              <span>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, inc.data.total)} of {inc.data.total}</span>
              <span className="space-x-1"><Button tone="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button tone="ghost" disabled={(page + 1) * PAGE >= inc.data.total} onClick={() => setPage(page + 1)}>Next</Button></span>
            </div>
          )}
        </div>
      </Card>

      <Card title={`Alert rules (${rules.data?.length ?? 0})`} action={writable && editing === null ? <Button tone="accent" onClick={() => setEditing('new')}><Plus className="h-3.5 w-3.5" aria-hidden /> New rule</Button> : undefined}>
        {rules.error && <ErrorBlock message={rules.error} onRetry={rules.reload} />}
        {rules.data && rules.data.length === 0 && <EmptyBlock title="No rules yet" hint="Without a rule, no alerts are generated." />}
        {rules.data && rules.data.length > 0 && (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500"><tr><th className="label py-1.5 font-normal">Rule</th><th className="label font-normal">Scope</th><th className="label font-normal">Thresholds</th><th className="label text-right font-normal">Incidents</th><th className="label pl-3 font-normal">Last evaluated</th><th /></tr></thead>
            <tbody>
              {rules.data.map((r) => (
                <tr key={r.id} className="border-t border-white/[0.05]">
                  <td className="py-2"><div className="flex items-center gap-2"><Switch checked={r.enabled} onChange={() => void toggle(r)} label={`${r.enabled ? 'Disable' : 'Enable'} ${r.name}`} disabled={!writable} /><span className={r.enabled ? 'text-slate-100' : 'text-slate-500'}>{r.name}</span></div></td>
                  <td className="text-slate-400">{scope(r)}</td>
                  <td className="font-mono text-2xs text-slate-400">≥{r.min_severity} · ≥{formatArea(r.min_area_m2)}{r.min_confidence != null && ` · score ≥${r.min_confidence}`}{r.categories?.length ? ` · ${r.categories.length} cat.` : ''}</td>
                  <td className="text-right font-mono text-slate-300">{r.incident_count}</td>
                  <td className="pl-3 text-2xs text-slate-500">{r.last_evaluated_at ? formatRelative(r.last_evaluated_at) : 'never'}</td>
                  <td className="space-x-1 text-right">{writable && <><Button tone="ghost" aria-label={`Edit ${r.name}`} onClick={() => setEditing(r)}><Pencil className="h-3.5 w-3.5" aria-hidden /></Button><Button tone="ghost" aria-label={`Delete ${r.name}`} onClick={() => void del(r)}><Trash2 className="h-3.5 w-3.5" aria-hidden /></Button></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <WeatherAlertsSection />

      {editing && <RuleEditor initial={editing === 'new' ? null : editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); refresh() }} />}
    </PageFrame>
  )
}
