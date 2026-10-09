'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, SEVERITIES, type Severity } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { categoryLabel, formatArea, formatDate, formatRelative, SEVERITY_COLOR } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Chip, DemoBadge, EmptyBlock, ErrorBlock, SeverityBadge, Skeleton, Stat } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'

interface Overview {
  analyses: { total: number; completed: number; running: number; failed: number }
  analyzed_area_m2: number; changed_area_m2: number; feature_count: number
  by_severity: Record<string, { count: number; area_m2: number }>
  by_category: Record<string, { count: number; area_m2: number }>
  series: { analysis_id: string; name: string; date: string; changed_area_m2: number | null; feature_count: number | null; method: string | null; is_demo: boolean }[]
  has_demo: boolean
}

export default function OverviewPage() {
  const router = useRouter()
  const analyses = useAppStore((s) => s.analyses)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const ov = useAsync(() => api.analytics.overview() as Promise<unknown> as Promise<Overview>, [analyses.length])
  const alerts = useAsync(() => api.alerts.incidents({ status: ['open'], limit: 5 }), [])
  const o = ov.data

  return (
    <PageFrame title="Overview" subtitle="Totals are computed from stored analysis results across everything you can access."
      actions={<Link href="/analyses/new" className="btn border-accent-dim bg-accent-surface text-accent hover:bg-[#1a4430]">New analysis</Link>}>
      {ov.error && <ErrorBlock message={ov.error} onRetry={ov.reload} />}
      {ov.loading && !o && <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>}
      {o && (
        <>
          {o.has_demo && <div className="flex items-center gap-2 rounded-md border border-demo/30 bg-demo/[0.06] px-3 py-2 text-xs text-slate-300"><DemoBadge /> Totals below include seeded demonstration analyses (synthetic imagery).</div>}
          <div className="grid grid-cols-2 gap-4 rounded-md border border-[color:var(--line-strong)] bg-ink-900/60 p-4 md:grid-cols-5">
            <Stat label="Completed analyses" value={o.analyses.completed} sub={`${o.analyses.running} running · ${o.analyses.failed} failed`} />
            <Stat label="Change polygons" value={o.feature_count.toLocaleString()} />
            <Stat label="Changed area" value={formatArea(o.changed_area_m2)} />
            <Stat label="Analysed area" value={formatArea(o.analyzed_area_m2)} />
            <Stat label="Changed fraction" value={o.analyzed_area_m2 > 0 ? `${((o.changed_area_m2 / o.analyzed_area_m2) * 100).toFixed(2)}%` : '-'} sub="of valid analysed pixels" />
          </div>

          {o.analyses.completed === 0 ? (
            <Card><EmptyBlock title="No completed analyses yet" hint="Upload a before/after GeoTIFF pair or acquire Sentinel-2 imagery to produce the first results." /></Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Polygons by severity (heuristic tier)">
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={SEVERITIES.map((s) => ({ severity: s, count: o.by_severity[s]?.count ?? 0 }))} margin={{ left: -16, right: 4, top: 4 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis dataKey="severity" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} contentStyle={{ background: '#101913', border: '1px solid rgba(255,255,255,0.1)', fontSize: 12 }} />
                    <Bar dataKey="count" name="Polygons" radius={[4, 4, 0, 0]}>
                      {SEVERITIES.map((s) => <Cell key={s} fill={SEVERITY_COLOR[s as Severity]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Changed area by category">
                <ul className="space-y-2">
                  {Object.entries(o.by_category).sort((a, b) => b[1].area_m2 - a[1].area_m2).map(([c, v]) => (
                    <li key={c} className="text-xs">
                      <div className="flex justify-between text-slate-300"><span>{categoryLabel(c)}</span><span className="font-mono text-slate-400">{v.count} · {formatArea(v.area_m2)}</span></div>
                      <div className="mt-1 h-1 rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-accent" style={{ width: `${o.changed_area_m2 > 0 ? (v.area_m2 / o.changed_area_m2) * 100 : 0}%` }} /></div>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-2xs text-slate-500">Categories are inferred from spectral indices or a model and are not human-verified.</p>
              </Card>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Recent analyses" action={<Link href="/analyses" className="text-2xs text-accent hover:underline">All analyses</Link>}>
              {analyses.length === 0 ? <EmptyBlock title="Nothing yet" /> : (
                <ul className="divide-y divide-[color:var(--line)]">
                  {analyses.slice(0, 6).map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                      <button className="focus-ring min-w-0 truncate text-left text-slate-200 hover:text-accent" onClick={() => { setActive(a.id); router.push('/map') }}>{a.name}</button>
                      <span className="flex shrink-0 items-center gap-2 text-2xs text-slate-500">{a.is_demo && <DemoBadge />}<Chip tone={a.status === 'completed' ? 'ok' : a.status === 'failed' ? 'danger' : 'accent'}>{a.status}</Chip>{formatRelative(a.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Open alerts" action={<Link href="/alerts" className="text-2xs text-accent hover:underline">Alert centre</Link>}>
              {alerts.error ? <p className="text-xs text-red-300">{alerts.error}</p> : alerts.data && alerts.data.items.length === 0 ? <EmptyBlock title="No open alerts" hint="Create a rule in the alert centre to be notified of matching changes." /> : (
                <ul className="divide-y divide-[color:var(--line)]">
                  {(alerts.data?.items ?? []).map((i) => (
                    <li key={i.id} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                      <span className="min-w-0 truncate text-slate-200">{i.title}</span>
                      <span className="flex shrink-0 items-center gap-2"><SeverityBadge severity={i.severity} /><span className="text-2xs text-slate-500">{formatDate(i.detected_at)}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </PageFrame>
  )
}
