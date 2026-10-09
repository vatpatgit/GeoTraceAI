'use client'

import { useState } from 'react'
import { AlertTriangle, ChevronDown, Download, MapPin, RotateCcw } from 'lucide-react'
import type { GgAction, GgBlock, GgJob, GgPairOption, GgScene, GgWorkflow } from '@/lib/api/geoguider'
import { cn } from '@/lib/format'
import { ProgressBar } from '@/components/ui/kit'

const fmtDate = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '–')
const cloud = (v: number | null) => (v === null ? 'n/a' : `${v.toFixed(0)}%`)

export interface BlockCtx {
  workflow: GgWorkflow | null
  busy: boolean
  onChoose: (pendingId: string, optionId: string) => void
  onAction: (a: GgAction) => void
  onRetry: () => void
  onCancel: () => void
}

function SceneLine({ s, label }: { s: GgScene; label: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="text-right text-slate-200">{fmtDate(s.acquired_at)} · cloud {cloud(s.cloud_cover_pct)}{s.coverage_of_aoi_pct != null && s.coverage_of_aoi_pct < 100 ? ` · covers ${s.coverage_of_aoi_pct.toFixed(0)}%` : ''}</span>
    </div>
  )
}

function PairCard({ o }: { o: GgPairOption }) {
  return (
    <li className={cn('rounded-md border px-2.5 py-2 text-2xs', o.recommended ? 'border-accent-dim bg-accent/[0.06]' : 'border-[color:var(--line-strong)] bg-black/20')}>
      <div className="mb-1 font-medium text-slate-200">{o.kind === 'series' ? `Series of ${o.pairs.length} comparisons` : o.recommended ? 'Recommended pair' : 'Alternative pair'}</div>
      {o.pairs.map((p, i) => (
        <div key={i} className="space-y-0.5 border-t border-[color:var(--line)] py-1 first:border-0">
          <SceneLine s={p.before} label="Before" />
          <SceneLine s={p.after} label="After" />
          <div className="text-slate-500">{p.seasonal_gap_days} days apart in the seasonal cycle · {p.separation_days.toLocaleString()} days between scenes</div>
        </div>
      ))}
    </li>
  )
}

function Result({ b, ctx }: { b: Extract<GgBlock, { type: 'result' }>; ctx: BlockCtx }) {
  const [open, setOpen] = useState(true)
  const titles: [keyof typeof b.sections, string][] = [['observed', 'Observed input data'], ['computed', 'Computed metrics'], ['predictions', 'Model predictions'], ['interpretation', 'Interpretation (hypotheses)'], ['limitations', 'Limitations']]
  return (
    <div className="rounded-md border border-[color:var(--line-strong)] bg-black/20 text-2xs">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="focus-ring flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left text-slate-200">
        <span className="font-medium">{b.name}</span><ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div className="space-y-2 border-t border-[color:var(--line)] px-2.5 py-2">
          {titles.map(([k, t]) => (
            <section key={k}>
              <h4 className="label mb-0.5">{t}</h4>
              <ul className="list-disc space-y-0.5 pl-4 text-slate-300">{b.sections[k].map((x, i) => <li key={i}>{x}</li>)}</ul>
            </section>
          ))}
          <div className="flex flex-wrap gap-1.5 pt-1">
            <button className="btn" onClick={() => ctx.onAction({ type: 'open_analysis', analysis_id: b.analysis_id })}><MapPin className="h-3.5 w-3.5" aria-hidden /> Show on map</button>
            {b.feature_count > 0 && <button className="btn" onClick={() => ctx.onAction({ type: 'download_export', path: `/analyses/${b.analysis_id}/export?format=geojson`, format: 'geojson', name: b.name })}><Download className="h-3.5 w-3.5" aria-hidden /> GeoJSON</button>}
          </div>
        </div>
      )}
    </div>
  )
}

function Progress({ b, ctx }: { b: Extract<GgBlock, { type: 'progress' }>; ctx: BlockCtx }) {
  const jobs: GgJob[] = (ctx.workflow?.jobs ?? []).filter((j) => b.analysis_ids.includes(j.id))
  const running = ctx.workflow?.cancellable
  return (
    <div className="space-y-1.5 rounded-md border border-[color:var(--line-strong)] bg-black/20 px-2.5 py-2 text-2xs" aria-live="polite">
      {jobs.length === 0 && <div className="text-slate-500">Reading job state…</div>}
      {jobs.map((j) => (
        <div key={j.id}>
          <div className="flex justify-between gap-2"><span className="truncate text-slate-300">{j.name ?? j.id.slice(0, 8)}</span><span className="text-slate-500">{j.status.replace('_', ' ')}</span></div>
          <ProgressBar value={j.progress} tone={j.status === 'failed' ? 'danger' : 'accent'} />
          <div className="text-slate-500">{j.error ?? j.stage ?? ''}</div>
        </div>
      ))}
      {running && <button className="btn" onClick={ctx.onCancel} disabled={ctx.busy}>Request cancellation</button>}
    </div>
  )
}

export function Block({ b, ctx, current }: { b: GgBlock; ctx: BlockCtx; current: boolean }) {
  switch (b.type) {
    case 'choices': {
      const live = current && ctx.workflow?.pending?.id === b.pending_id
      return (
        <div role="group" aria-label={b.prompt} className="flex flex-col gap-1">
          {b.options.map((o) => (
            <button key={o.id} disabled={!live || ctx.busy} onClick={() => ctx.onChoose(b.pending_id, o.id)} className="btn justify-start text-left disabled:opacity-40">
              <span className="font-medium">{o.label}</span>{o.description && <span className="ml-1 text-slate-500">{o.description}</span>}
            </button>
          ))}
        </div>
      )
    }
    case 'aoi': return <div className="rounded-md border border-[color:var(--line-strong)] bg-black/20 px-2.5 py-1.5 text-2xs text-slate-300"><MapPin className="mr-1 inline h-3 w-3 text-accent" aria-hidden />{b.aoi.name} · {b.aoi.area_km2.toLocaleString()} km² · [{b.aoi.bbox.join(', ')}]</div>
    case 'coverage':
      return (
        <table className="w-full text-2xs"><caption className="label mb-1 text-left">Scenes found per sub-period ({b.provider}, cloud ≤ {b.max_cloud}%)</caption>
          <thead><tr className="text-left text-slate-500"><th className="font-normal">From</th><th className="font-normal">To</th><th className="text-right font-normal">Scenes</th><th className="text-right font-normal">Lowest cloud</th></tr></thead>
          <tbody>{b.rows.map((r) => (
            <tr key={r.start} className="border-t border-[color:var(--line)] text-slate-300"><td>{fmtDate(r.start)}</td><td>{fmtDate(r.end)}</td>
              <td className="text-right">{r.failed ? 'search failed' : `${r.count}${r.truncated ? '+' : ''}`}</td><td className="text-right">{r.best_cloud == null ? '–' : `${r.best_cloud.toFixed(0)}%`}</td></tr>
          ))}</tbody>
        </table>
      )
    case 'scene_pairs': return <ul className="space-y-1.5">{b.options.map((o) => <PairCard key={o.id} o={o} />)}</ul>
    case 'scene_list':
      return <ul className="space-y-1 text-2xs">{b.scenes.map((s) => <li key={s.product_id} className="rounded border border-[color:var(--line-strong)] bg-black/20 px-2 py-1 text-slate-300">{fmtDate(s.acquired_at)} · cloud {cloud(s.cloud_cover_pct)} · {s.platform ?? 'Sentinel-2'}{s.resolution_m ? ` · ${s.resolution_m} m` : ''}</li>)}</ul>
    case 'plan':
      return <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 rounded-md border border-[color:var(--line-strong)] bg-black/20 px-2.5 py-2 text-2xs">{b.rows.map(([k, v]) => <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd className="text-slate-200">{v}</dd></div>)}</dl>
    case 'progress': return <Progress b={b} ctx={ctx} />
    case 'period_summary':
      return <table className="w-full text-2xs"><thead><tr className="text-left text-slate-500"><th className="font-normal">Comparison</th><th className="text-right font-normal">Polygons</th><th className="text-right font-normal">Changed area</th></tr></thead>
        <tbody>{b.rows.map((r, i) => <tr key={i} className="border-t border-[color:var(--line)] text-slate-300"><td>{r[0]}</td><td className="text-right">{r[1]}</td><td className="text-right">{r[2]}</td></tr>)}</tbody></table>
    case 'result': return <Result b={b} ctx={ctx} />
    case 'facts':
      return <div className="rounded-md border border-[color:var(--line-strong)] bg-black/20 px-2.5 py-2 text-2xs"><ul className="list-disc space-y-0.5 pl-4 text-slate-300">{b.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
        {b.caveats.length > 0 && <p className="mt-1.5 text-slate-500">{b.caveats.join(' ')}</p>}</div>
    case 'weather':
      return (
        <div className="rounded-md border border-[color:var(--line-strong)] bg-black/20 px-2.5 py-2 text-2xs">
          <div className="label mb-1">Weather alerts · {b.aoi} (provider forecasts, not satellite detections)</div>
          {b.alerts.length === 0 ? <div className="text-slate-500">{b.configured ? 'No active alerts.' : 'Integration not configured.'}</div> :
            <ul className="space-y-1">{b.alerts.map((a) => <li key={a.id} className="text-slate-300"><span className="font-medium">{a.title}</span> · {a.severity} · {fmtDate(a.start)} → {fmtDate(a.end)}</li>)}</ul>}
        </div>
      )
    case 'export':
      return <div className="flex flex-wrap gap-1.5">{b.items.map((it) => <button key={it.format} className="btn" onClick={() => ctx.onAction({ type: 'download_export', path: it.path, format: it.format, name: it.name })}><Download className="h-3.5 w-3.5" aria-hidden /> {it.format === 'pdf' ? 'PDF report' : it.format.toUpperCase()}</button>)}</div>
    case 'error':
      return (
        <div role="alert" className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/[0.06] px-2.5 py-2 text-2xs text-red-200">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /><span className="flex-1">{b.message}</span>
          {b.retryable && current && <button className="btn" onClick={ctx.onRetry} disabled={ctx.busy}><RotateCcw className="h-3 w-3" aria-hidden /> Retry</button>}
        </div>
      )
    default: return null
  }
}
