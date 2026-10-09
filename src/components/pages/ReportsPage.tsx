'use client'

import { useState } from 'react'
import { Download, FileText } from 'lucide-react'
import { api, ApiError, type Analysis, type ExportFormat } from '@/lib/api'
import { formatArea, formatDate } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, DemoBadge, EmptyBlock } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'

function Row({ a }: { a: Analysis }) {
  const toast = useAppStore((s) => s.toast)
  const [busy, setBusy] = useState<string | null>(null)
  async function run(key: string, fn: () => Promise<{ filename: string }>) {
    setBusy(key)
    try { const r = await fn(); toast('success', `Downloaded ${r.filename}`) } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Download failed') } finally { setBusy(null) }
  }
  const fmt = (f: 'json' | 'csv' | 'pdf') => (
    <Button key={f} loading={busy === f} onClick={() => void run(f, () => api.reports.download(a.id, f))}><FileText className="h-3.5 w-3.5" aria-hidden /> {f.toUpperCase()}</Button>
  )
  const exp = (f: ExportFormat, label: string) => (
    <Button key={f} loading={busy === f} onClick={() => void run(f, () => api.analyses.export(a.id, f))}><Download className="h-3.5 w-3.5" aria-hidden /> {label}</Button>
  )
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.05] px-3 py-3 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-xs text-slate-100">{a.name}{a.is_demo && <DemoBadge />}</div>
        <div className="mt-0.5 text-2xs text-slate-500">{formatDate(a.before_date)} → {formatDate(a.after_date)} · {a.summary?.feature_count ?? 0} polygons · {formatArea(a.summary?.total_changed_area_m2)} · {a.method?.replace(/_/g, ' ')}</div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="label mr-1">Report</span>{(['pdf', 'csv', 'json'] as const).map(fmt)}
        <span className="label ml-3 mr-1">Detections</span>{exp('geojson', 'GeoJSON')}{exp('gpkg', 'GeoPackage')}{exp('csv', 'CSV')}
      </div>
    </li>
  )
}

export default function ReportsPage() {
  const done = useAppStore((s) => s.analyses).filter((a) => a.status === 'completed')
  return (
    <PageFrame wide title="Reports & exports" subtitle="Every report is generated from the stored analysis record: imagery provenance, method, measured totals, the largest detections and quality warnings. Exports contain exactly the stored polygons.">
      <Card>
        {done.length === 0 ? <EmptyBlock title="No completed analyses to report on" hint="Reports are produced from completed analyses." /> : <ul className="-m-3">{done.map((a) => <Row key={a.id} a={a} />)}</ul>}
      </Card>
      <p className="text-2xs text-slate-500">Reports describe observed image differences. Categories and severity are heuristic or model-inferred and require human verification; severity is not a calibrated probability. Reports for demo analyses are marked as synthetic.</p>
    </PageFrame>
  )
}
