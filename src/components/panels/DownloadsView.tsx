'use client'

import { useState } from 'react'
import { Download } from 'lucide-react'
import { api, ApiError, type ExportFormat, type FeatureFilters } from '@/lib/api'
import { hasActiveFilters, selectActiveAnalysis, toFeatureFilters, useAppStore } from '@/store/useAppStore'
import { Button, EmptyBlock } from '@/components/ui/kit'

const FORMATS: { id: ExportFormat; label: string; hint: string }[] = [
  { id: 'geojson', label: 'GeoJSON', hint: 'RFC 7946, WGS 84' },
  { id: 'gpkg', label: 'GeoPackage', hint: 'layer + metadata tables' },
  { id: 'csv', label: 'CSV', hint: 'attributes + WKT' },
]

export default function DownloadsView() {
  const analysis = useAppStore(selectActiveAnalysis)
  const filters = useAppStore((s) => s.filters)
  const selected = useAppStore((s) => s.selectedFeatureId)
  const toast = useAppStore((s) => s.toast)
  const [busy, setBusy] = useState<string | null>(null)
  if (!analysis) return <EmptyBlock title="No analysis selected" />
  if (analysis.status !== 'completed') return <EmptyBlock title="Exports unlock when processing completes" />

  const scopes: { id: string; label: string; filters: FeatureFilters; disabled?: boolean; hint: string }[] = [
    { id: 'all', label: 'All features', filters: {}, hint: `${analysis.summary?.feature_count ?? 0} polygons` },
    { id: 'filtered', label: 'Active filters', filters: toFeatureFilters(filters), disabled: !hasActiveFilters(filters), hint: hasActiveFilters(filters) ? 'exactly what the list shows' : 'no filter active' },
    { id: 'selected', label: 'Selected feature', filters: { ids: selected ? [selected] : [] }, disabled: !selected, hint: selected ? '1 polygon' : 'none selected' },
  ]

  async function run(scopeId: string, f: FeatureFilters, fmt: ExportFormat) {
    const key = `${scopeId}-${fmt}`
    setBusy(key)
    try {
      const r = await api.analyses.export(analysis!.id, fmt, f)
      toast('success', `${fmt.toUpperCase()} downloaded: ${r.featureCount ?? '?'} feature(s) (${r.filename})`)
    } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Export failed') } finally { setBusy(null) }
  }

  return (
    <div className="grid h-full min-h-0 gap-6 overflow-y-auto p-3 lg:grid-cols-[2fr_1fr]">
      <div>
        <h3 className="label mb-2">Vector results</h3>
        <div className="overflow-hidden rounded-md border border-white/[0.07]">
          {scopes.map((s) => (
            <div key={s.id} className="hairline-b flex flex-wrap items-center gap-2 px-3 py-2 last:border-b-0">
              <div className="min-w-[140px] flex-1"><div className="text-xs text-slate-200">{s.label}</div><div className="text-2xs text-slate-500">{s.hint}</div></div>
              {FORMATS.map((f) => (
                <Button key={f.id} disabled={s.disabled} loading={busy === `${s.id}-${f.id}`} title={f.hint} onClick={() => run(s.id, s.filters, f.id)}><Download className="h-3 w-3" aria-hidden /> {f.label}</Button>
              ))}
            </div>
          ))}
        </div>
        <p className="mt-2 text-2xs text-slate-500">Files include area (m2), centroid, magnitude, severity, dates, review status, source-imagery provenance and the analysis method.{analysis.is_demo ? ' Demo data is flagged inside the file.' : ''}</p>
      </div>
      <div>
        <h3 className="label mb-2">Rasters (GeoTIFF)</h3>
        <ul className="space-y-1.5">
          {analysis.artifacts.filter((a) => ['change_mask', 'change_score', 'delta_ndvi'].includes(a)).map((a) => (
            <li key={a}><Button className="w-full justify-start" onClick={() => void api.analyses.downloadArtifact(analysis.id, a).catch((e) => toast('error', e.message))}><Download className="h-3 w-3" aria-hidden /> {a.replace(/_/g, ' ')}</Button></li>
          ))}
        </ul>
      </div>
    </div>
  )
}
