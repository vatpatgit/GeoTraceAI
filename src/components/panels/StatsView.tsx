'use client'

import { categoryLabel, formatArea, formatPct, SEVERITY_COLOR } from '@/lib/format'
import { SEVERITIES } from '@/lib/api'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { Chip, EmptyBlock, Stat } from '@/components/ui/kit'

/** Horizontal bar list: label + value are always text (colour is never the only carrier of identity). */
export function BarList({ rows, format, ariaLabel }: { rows: { label: string; value: number; color: string; note?: string }[]; format: (v: number) => string; ariaLabel: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9)
  return (
    <ul aria-label={ariaLabel} className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.label} className="grid grid-cols-[110px_1fr_auto] items-center gap-2 text-xs">
          <span className="truncate text-slate-300">{r.label}</span>
          <span className="h-2 rounded-sm bg-white/[0.04]"><span className="block h-2 rounded-sm" style={{ width: `${Math.max((r.value / max) * 100, r.value > 0 ? 2 : 0)}%`, background: r.color }} /></span>
          <span className="w-24 text-right font-mono text-slate-200">{format(r.value)}{r.note ? <span className="ml-1 text-slate-500">{r.note}</span> : null}</span>
        </li>
      ))}
    </ul>
  )
}

export default function StatsView() {
  const analysis = useAppStore(selectActiveAnalysis)
  if (!analysis) return <EmptyBlock title="No analysis selected" />
  const s = analysis.summary
  if (!s) return <EmptyBlock title="No statistics yet" hint="Statistics are computed from the stored detections once processing completes." />
  const det = analysis.processing?.detection
  const test = (analysis.processing?.detection?.details as { model_metrics_heldout?: { f1: number; precision: number; recall: number; num_samples: number } } | undefined)?.model_metrics_heldout
  const sevRows = SEVERITIES.map((k) => ({ label: k, value: s.by_severity[k] ?? 0, color: SEVERITY_COLOR[k], note: formatArea(s.area_by_severity_m2[k] ?? 0) }))
  const catRows = Object.entries(s.by_category).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: categoryLabel(k), value: s.area_by_category_m2[k] ?? 0, color: '#2DD4BF', note: `${v}x` }))
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 overflow-y-auto p-3 lg:grid-cols-[1fr_1.2fr_1.2fr]">
      <div className="grid grid-cols-2 content-start gap-3">
        <Stat label="Polygons" value={s.feature_count.toLocaleString('en-US')} />
        <Stat label="Changed area" value={formatArea(s.total_changed_area_m2)} sub={`${formatPct(s.changed_fraction, 2)} of analysed`} />
        <Stat label="Analysed area" value={formatArea(s.analyzed_area_m2)} sub={`${formatPct(s.valid_fraction, 0)} valid pixels`} />
        <Stat label="Grid" value={`${s.pixel_size_m} m`} sub={`${s.grid.width} x ${s.grid.height} px, EPSG:${s.grid.crs_epsg}`} />
        <div className="col-span-2 flex flex-wrap gap-1.5">
          <Chip tone="accent">{analysis.method?.replace(/_/g, ' ')}</Chip>
          {det?.confidence_kind ? <Chip>score: uncalibrated model probability</Chip> : <Chip>no confidence score (baseline)</Chip>}
        </div>
        {test && <p className="col-span-2 text-2xs text-slate-500">Model held-out benchmark (not this scene): F1 {test.f1.toFixed(2)}, precision {test.precision.toFixed(2)}, recall {test.recall.toFixed(2)} on {test.num_samples} samples of aerial imagery.</p>}
      </div>
      <div><h3 className="label mb-2">By severity (count, area)</h3><BarList ariaLabel="Detections by severity" rows={sevRows} format={(v) => String(v)} /></div>
      <div><h3 className="label mb-2">By category (area, count)</h3>{catRows.length ? <BarList ariaLabel="Changed area by category" rows={catRows} format={formatArea} /> : <p className="text-xs text-slate-600">No detections.</p>}</div>
    </div>
  )
}
