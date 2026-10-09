'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Check, MapPin, X } from 'lucide-react'
import { api, ApiError, SEVERITIES, type ChangeFeature, type ReviewStatus, type Severity } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { basisLabel, categoryLabel, cn, formatArea, formatPct } from '@/lib/format'
import { canWrite } from '@/lib/auth'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { Button, Chip, DemoBadge, EmptyBlock, ErrorBlock, inputCls, SeverityBadge, Skeleton } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'

const PAGE = 30
const REVIEWS: ReviewStatus[] = ['unreviewed', 'confirmed', 'rejected']
type Sort = 'area_desc' | 'severity_desc' | 'confidence_desc' | 'seq'

export default function ChangesPage() {
  const router = useRouter()
  const analyses = useAppStore((s) => s.analyses).filter((a) => a.status === 'completed')
  const active = useAppStore(selectActiveAnalysis)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const selectFeature = useAppStore((s) => s.selectFeature)
  const bump = useAppStore((s) => s.bumpFeatures)
  const user = useAppStore((s) => s.authUser)
  const toast = useAppStore((s) => s.toast)
  const writable = canWrite(user?.role)

  const [pick, setPick] = useState<string | null>(null)
  const current = analyses.find((a) => a.id === (pick ?? active?.id)) ?? analyses[0] ?? null
  const [sev, setSev] = useState<Severity[]>([])
  const [rev, setRev] = useState<ReviewStatus[]>([])
  const [category, setCategory] = useState('')
  const [sort, setSort] = useState<Sort>('area_desc')
  const [page, setPage] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)

  const res = useAsync(() => (current
    ? api.analyses.features(current.id, { severity: sev.length ? sev : undefined, review_status: rev.length ? rev : undefined, category: category ? [category] : undefined, sort }, { limit: PAGE, offset: page * PAGE })
    : Promise.resolve(null)), [current?.id, sev.join(), rev.join(), category, sort, page])

  const toggle = <T,>(list: T[], v: T, set: (l: T[]) => void) => { set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]); setPage(0) }

  async function review(f: ChangeFeature, status: ReviewStatus) {
    if (!current) return
    setBusy(f.id)
    try { await api.analyses.review(current.id, f.id, status); bump(); res.reload() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Review failed') } finally { setBusy(null) }
  }
  function show(f: ChangeFeature) {
    if (!current) return
    setActive(current.id); selectFeature(f.id, { fly: true, bbox: f.bbox }); router.push('/map')
  }

  const cats = Object.keys(current?.summary?.by_category ?? {})
  const pill = (on: boolean) => cn('focus-ring rounded border px-1.5 py-0.5 font-mono text-2xs uppercase', on ? 'border-accent-dim bg-accent-surface text-accent' : 'border-[color:var(--line-strong)] text-slate-500 hover:text-slate-200')

  return (
    <PageFrame wide title="Change intelligence" subtitle="Every detected polygon of an analysis with its measured attributes. Review status is a human decision; categories and severity are inferred.">
      {analyses.length === 0 ? <Card><EmptyBlock title="No completed analyses" hint="Detections appear after an analysis completes." /></Card> : (
        <>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label htmlFor="ch-an" className="label">Analysis</label>
            <select id="ch-an" className={cn(inputCls, 'max-w-sm')} value={current?.id ?? ''} onChange={(e) => { setPick(e.target.value); setPage(0) }}>{analyses.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
            {current?.is_demo && <DemoBadge />}
            <div role="group" aria-label="Severity filter" className="flex gap-1">{SEVERITIES.map((s) => <button key={s} aria-pressed={sev.includes(s)} className={pill(sev.includes(s))} onClick={() => toggle(sev, s, setSev)}>{s}</button>)}</div>
            <div role="group" aria-label="Review filter" className="flex gap-1">{REVIEWS.map((r) => <button key={r} aria-pressed={rev.includes(r)} className={pill(rev.includes(r))} onClick={() => toggle(rev, r, setRev)}>{r}</button>)}</div>
            <select aria-label="Category filter" className={cn(inputCls, 'w-44')} value={category} onChange={(e) => { setCategory(e.target.value); setPage(0) }}><option value="">All categories</option>{cats.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}</select>
            <select aria-label="Sort" className={cn(inputCls, 'w-40')} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="area_desc">Largest area</option><option value="severity_desc">Highest severity</option><option value="confidence_desc">Highest score</option><option value="seq">ID order</option>
            </select>
          </div>

          <Card>
            <div className="-m-3 overflow-x-auto">
              {res.error && <ErrorBlock message={res.error} onRetry={res.reload} />}
              {res.loading && !res.data && <div className="space-y-2 p-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>}
              {res.data && res.data.items.length === 0 && <EmptyBlock title="No detections match these filters" />}
              {res.data && res.data.items.length > 0 && (
                <table className="w-full min-w-[820px] text-left text-xs">
                  <thead className="text-slate-500"><tr className="hairline-b"><th className="label px-3 py-2 font-normal">#</th><th className="label font-normal">Category</th><th className="label font-normal">Severity</th><th className="label text-right font-normal">Area</th><th className="label text-right font-normal">Magnitude</th><th className="label text-right font-normal">Score</th><th className="label pl-4 font-normal">Review</th><th /></tr></thead>
                  <tbody>
                    {res.data.items.map((f) => (
                      <tr key={f.id} className="border-b border-[color:var(--line)] hover:bg-ink-800/70">
                        <td className="px-3 py-2 font-mono text-slate-400">{f.seq}</td>
                        <td><div className="text-slate-200">{categoryLabel(f.category)}</div><div className="text-2xs text-slate-500">{basisLabel(f.category_basis)}</div></td>
                        <td><SeverityBadge severity={f.severity} /></td>
                        <td className="text-right font-mono text-slate-200">{formatArea(f.area_m2)}</td>
                        <td className="text-right font-mono text-slate-300">{f.magnitude.toFixed(2)}</td>
                        <td className="text-right font-mono text-slate-300" title={f.confidence == null ? 'This detector produces no score' : 'Uncalibrated model score, not a probability'}>{f.confidence == null ? 'n/a' : formatPct(f.confidence, 0)}</td>
                        <td className="pl-4"><Chip tone={f.review_status === 'confirmed' ? 'ok' : f.review_status === 'rejected' ? 'danger' : 'default'}>{f.review_status}</Chip></td>
                        <td className="space-x-1 whitespace-nowrap pr-2 text-right">
                          <Button tone="ghost" aria-label={`Show detection ${f.seq} on the map`} onClick={() => show(f)}><MapPin className="h-3.5 w-3.5" aria-hidden /></Button>
                          {writable && <>
                            <Button tone="ghost" aria-label={`Confirm detection ${f.seq}`} loading={busy === f.id} disabled={f.review_status === 'confirmed'} onClick={() => void review(f, 'confirmed')}><Check className="h-3.5 w-3.5" aria-hidden /></Button>
                            <Button tone="ghost" aria-label={`Reject detection ${f.seq}`} loading={busy === f.id} disabled={f.review_status === 'rejected'} onClick={() => void review(f, 'rejected')}><X className="h-3.5 w-3.5" aria-hidden /></Button>
                          </>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {res.data && res.data.total > PAGE && (
                <div className="flex items-center justify-between border-t border-[color:var(--line)] px-3 py-2 text-2xs text-slate-500">
                  <span>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, res.data.total)} of {res.data.total}</span>
                  <span className="space-x-1"><Button tone="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button tone="ghost" disabled={(page + 1) * PAGE >= res.data.total} onClick={() => setPage(page + 1)}>Next</Button></span>
                </div>
              )}
            </div>
          </Card>
        </>
      )}
    </PageFrame>
  )
}
