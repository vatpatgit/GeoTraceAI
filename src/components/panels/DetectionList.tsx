'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowDownAZ, FilterX } from 'lucide-react'
import { api, ApiError, SEVERITIES, type ChangeFeature, type Severity } from '@/lib/api'
import { categoryLabel, cn, formatArea, formatPct } from '@/lib/format'
import { hasActiveFilters, selectActiveAnalysis, toFeatureFilters, useAppStore } from '@/store/useAppStore'
import { Button, Chip, EmptyBlock, ErrorBlock, SeverityBadge, SeverityDot, Skeleton } from '@/components/ui/kit'

const PAGE = 50
type Sort = 'area_desc' | 'severity_desc' | 'confidence_desc' | 'seq'
const SORTS: { value: Sort; label: string }[] = [
  { value: 'area_desc', label: 'Largest area' }, { value: 'severity_desc', label: 'Highest severity' },
  { value: 'confidence_desc', label: 'Highest score' }, { value: 'seq', label: 'ID order' },
]

export default function DetectionList() {
  const analysis = useAppStore(selectActiveAnalysis)
  const filters = useAppStore((s) => s.filters)
  const setFilters = useAppStore((s) => s.setFilters)
  const resetFilters = useAppStore((s) => s.resetFilters)
  const version = useAppStore((s) => s.featuresVersion)
  const selectedId = useAppStore((s) => s.selectedFeatureId)
  const selectFeature = useAppStore((s) => s.selectFeature)
  const setHovered = useAppStore((s) => s.setHoveredFeature)

  const [items, setItems] = useState<ChangeFeature[]>([])
  const [total, setTotal] = useState(0)
  const [sort, setSort] = useState<Sort>('area_desc')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async (offset: number, replace: boolean) => {
    if (!analysis || analysis.status !== 'completed') { setItems([]); setTotal(0); return }
    setLoading(true); setError(null)
    try {
      const page = await api.analyses.features(analysis.id, { ...toFeatureFilters(filters), sort }, { limit: PAGE, offset })
      setTotal(page.total)
      setItems((prev) => (replace ? page.items : [...prev, ...page.items]))
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Failed to load detections') } finally { setLoading(false) }
  }, [analysis, filters, sort])

  useEffect(() => { void load(0, true) }, [load, version])

  const select = (f: ChangeFeature) => selectFeature(f.id, { fly: true, bbox: f.bbox })

  function onKey(e: React.KeyboardEvent) {
    if (!items.length) return
    const i = items.findIndex((f) => f.id === selectedId)
    if (e.key === 'ArrowDown') { e.preventDefault(); select(items[Math.min(i + 1, items.length - 1)]) }
    if (e.key === 'ArrowUp') { e.preventDefault(); select(items[Math.max(i - 1, 0)]) }
  }

  const toggleSev = (s: Severity) => setFilters({ severities: filters.severities.includes(s) ? filters.severities.filter((x) => x !== s) : [...filters.severities, s] })
  const categories = Object.keys(analysis?.summary?.by_category ?? {})

  if (!analysis) return <EmptyBlock title="No analysis selected" hint="Pick an analysis from the top bar, or start a new one." />
  if (analysis.status !== 'completed') return <EmptyBlock title={`Analysis is ${analysis.status.replace(/_/g, ' ')}`} hint="Detections appear here once processing completes. See the Progress tab." />

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="hairline-b flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-1.5">
        <div className="flex items-center gap-1" role="group" aria-label="Filter by severity">
          {SEVERITIES.map((s) => (
            <button key={s} onClick={() => toggleSev(s)} aria-pressed={filters.severities.includes(s)} className={cn('focus-ring flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-2xs uppercase tracking-wider transition-colors', filters.severities.includes(s) ? 'border-white/30 bg-white/10 text-slate-100' : 'border-[color:var(--line-strong)] text-slate-500 hover:text-slate-200')}>
              <SeverityDot severity={s} />{s}{analysis.summary?.by_severity?.[s] ? <span className="text-slate-500">{analysis.summary.by_severity[s]}</span> : null}
            </button>
          ))}
        </div>
        {categories.length > 1 && (
          <select aria-label="Filter by category" value={filters.categories[0] ?? ''} onChange={(e) => setFilters({ categories: e.target.value ? [e.target.value] : [] })} className="focus-ring rounded border border-[color:var(--line-strong)] bg-black/30 px-1.5 py-0.5 text-2xs text-slate-300">
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
          </select>
        )}
        <label className="flex items-center gap-1 text-2xs text-slate-500">Min area
          <input type="number" min={0} step={100} aria-label="Minimum area in square metres" value={filters.minAreaM2 ?? ''} onChange={(e) => setFilters({ minAreaM2: e.target.value === '' ? null : Math.max(0, Number(e.target.value)) })} placeholder="m2" className="focus-ring w-16 rounded border border-[color:var(--line-strong)] bg-black/30 px-1 py-0.5 font-mono text-2xs text-slate-200" />
        </label>
        <select aria-label="Filter by review status" value={filters.reviewStatus[0] ?? ''} onChange={(e) => setFilters({ reviewStatus: e.target.value ? [e.target.value as 'unreviewed'] : [] })} className="focus-ring rounded border border-[color:var(--line-strong)] bg-black/30 px-1.5 py-0.5 text-2xs text-slate-300">
          <option value="">Any review state</option><option value="unreviewed">Needs review</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option>
        </select>
        <span className="flex items-center gap-1 text-2xs text-slate-500"><ArrowDownAZ className="h-3 w-3" aria-hidden />
          <select aria-label="Sort detections" value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="focus-ring rounded border border-[color:var(--line-strong)] bg-black/30 px-1.5 py-0.5 text-2xs text-slate-300">{SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
        </span>
        {hasActiveFilters(filters) && <Button tone="ghost" className="px-1.5 py-0.5 text-2xs" onClick={resetFilters}><FilterX className="h-3 w-3" aria-hidden /> Clear</Button>}
        <span className="ml-auto font-mono text-2xs text-slate-500" aria-live="polite">{total.toLocaleString('en-US')} detection{total === 1 ? '' : 's'}{hasActiveFilters(filters) ? ' (filtered)' : ''}</span>
      </div>

      <div ref={listRef} tabIndex={0} onKeyDown={onKey} role="listbox" aria-label="Detections" className="focus-ring min-h-0 flex-1 overflow-y-auto">
        {error && <ErrorBlock message={error} onRetry={() => void load(0, true)} />}
        {!error && loading && items.length === 0 && <div className="space-y-1 p-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-7 w-full" />)}</div>}
        {!error && !loading && items.length === 0 && (
          <EmptyBlock title={hasActiveFilters(filters) ? 'No detections match these filters' : 'No change detected'} hint={hasActiveFilters(filters) ? 'Loosen or clear the filters.' : 'No change exceeded the threshold after filtering. That is a valid result, not an error.'} action={hasActiveFilters(filters) ? <Button onClick={resetFilters}>Clear filters</Button> : undefined} />
        )}
        {items.length > 0 && (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-ink-850 text-slate-500"><tr className="hairline-b">
              <th className="label w-8 py-1 pl-3 font-normal">#</th><th className="label py-1 font-normal">Severity</th><th className="label py-1 font-normal">Category</th>
              <th className="label py-1 text-right font-normal">Area</th><th className="label py-1 text-right font-normal" title="Model score (uncalibrated) when the detector provides one; otherwise the normalised change magnitude (0-1). Neither is a probability.">Score / mag.</th><th className="label py-1 pr-3 text-right font-normal">Review</th>
            </tr></thead>
            <tbody>
              {items.map((f) => (
                <tr key={f.id} role="option" aria-selected={f.id === selectedId} onClick={() => select(f)} onMouseEnter={() => setHovered(f.id)} onMouseLeave={() => setHovered(null)}
                  className={cn('cursor-pointer border-b border-[color:var(--line)] hover:bg-ink-700', f.id === selectedId && 'bg-accent/[0.09]')}>
                  <td className="py-1 pl-3 font-mono text-slate-500">{f.seq}</td>
                  <td className="py-1"><SeverityBadge severity={f.severity} /></td>
                  <td className="py-1 text-slate-300">{categoryLabel(f.category)}</td>
                  <td className="py-1 text-right font-mono text-slate-200">{formatArea(f.area_m2)}</td>
                  <td className="py-1 text-right font-mono text-slate-400" title={f.confidence !== null ? 'Uncalibrated model score, not a probability' : 'Normalised change magnitude (0-1); this detector produces no confidence'}>{f.confidence !== null ? formatPct(f.confidence, 0) : f.magnitude.toFixed(2)}</td>
                  <td className="py-1 pr-3 text-right"><Chip tone={f.review_status === 'confirmed' ? 'ok' : f.review_status === 'rejected' ? 'danger' : 'default'}>{f.review_status === 'unreviewed' ? 'todo' : f.review_status}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {items.length < total && !error && <div className="flex justify-center p-2"><Button loading={loading} onClick={() => void load(items.length, false)}>Load more ({total - items.length} remaining)</Button></div>}
      </div>
    </div>
  )
}
