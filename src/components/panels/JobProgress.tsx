'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleDot, Info, RotateCcw, Square, XCircle } from 'lucide-react'
import { api, ApiError, type AnalysisEvent, type Issue } from '@/lib/api'
import { canWrite } from '@/lib/auth'
import { cn, formatDate, formatDuration, isActiveStatus, STATUS_LABEL } from '@/lib/format'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { Button, Chip, EmptyBlock, ProgressBar } from '@/components/ui/kit'

const STAGES = ['queued', 'validating', 'preprocessing', 'detecting_changes', 'polygonizing', 'evaluating_alerts', 'completed'] as const

export default function JobProgress() {
  const analysis = useAppStore(selectActiveAnalysis)
  const upsert = useAppStore((s) => s.upsertAnalysis)
  const toast = useAppStore((s) => s.toast)
  const user = useAppStore((s) => s.authUser)
  const [events, setEvents] = useState<AnalysisEvent[]>([])
  const [busy, setBusy] = useState(false)

  const analysisId = analysis?.id
  const analysisStatus = analysis?.status
  useEffect(() => {
    if (!analysisId || !analysisStatus) { setEvents([]); return }
    let alive = true
    const load = () => api.analyses.events(analysisId).then((e) => alive && setEvents(e)).catch(() => undefined)
    void load()
    if (!isActiveStatus(analysisStatus)) return () => { alive = false }
    const t = setInterval(load, 2000)
    return () => { alive = false; clearInterval(t) }
  }, [analysisId, analysisStatus])

  if (!analysis) return <EmptyBlock title="No analysis selected" />
  const active = isActiveStatus(analysis.status)
  const idx = STAGES.indexOf(analysis.status as (typeof STAGES)[number])
  const issues: Issue[] = (analysis.warnings ?? []).filter((w) => w.level !== 'info' || w.code !== 'cloud_masked')
  const timings = analysis.processing?.timings
  const reg = analysis.processing?.registration

  async function act(fn: () => Promise<unknown>, ok: string) {
    setBusy(true)
    try { upsert((await fn()) as never); toast('success', ok) } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Action failed') } finally { setBusy(false) }
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-0 overflow-y-auto md:grid-cols-[1.1fr_1fr]">
      <div className="hairline-b border-[color:var(--line)] p-3 md:border-b-0 md:border-r">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2"><Chip tone={analysis.status === 'failed' ? 'danger' : analysis.status === 'completed' ? 'ok' : 'accent'}>{STATUS_LABEL[analysis.status]}</Chip><span className="font-mono text-2xs text-slate-500">{Math.round(analysis.progress * 100)}%</span></div>
          {canWrite(user?.role) && (
            <div className="flex gap-1.5">
              {active && <Button tone="danger" disabled={busy || analysis.cancel_requested} onClick={() => act(() => api.analyses.cancel(analysis.id), 'Cancellation requested')}><Square className="h-3 w-3" aria-hidden /> {analysis.cancel_requested ? 'Cancelling...' : 'Cancel'}</Button>}
              {(analysis.status === 'failed' || analysis.status === 'cancelled') && <Button tone="accent" disabled={busy} onClick={() => act(() => api.analyses.retry(analysis.id), 'Re-queued')}><RotateCcw className="h-3 w-3" aria-hidden /> Retry</Button>}
            </div>
          )}
        </div>
        <ProgressBar value={analysis.progress} tone={analysis.status === 'failed' ? 'danger' : 'accent'} indeterminate={analysis.status === 'queued'} />
        <p className="mt-1.5 text-xs text-slate-400">{analysis.stage_message ?? ''}</p>
        {analysis.error && (
          <div role="alert" className="mt-2 rounded border border-red-500/25 bg-red-500/[0.06] p-2.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-red-300"><XCircle className="h-3.5 w-3.5" aria-hidden />{analysis.error.code.replace(/_/g, ' ')}</div>
            <p className="mt-1 text-xs2 text-slate-300">{analysis.error.message}</p>
          </div>
        )}
        <ol className="mt-3 space-y-1" aria-label="Pipeline stages">
          {STAGES.map((s, i) => {
            const done = analysis.status === 'completed' || (idx !== -1 && i < idx)
            const current = s === analysis.status && active
            return (
              <li key={s} className={cn('flex items-center gap-2 text-xs', done ? 'text-slate-300' : current ? 'text-accent' : 'text-slate-600')}>
                {done ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-hidden /> : current ? <CircleDot className="h-3.5 w-3.5 animate-pulse-dot" aria-hidden /> : <CircleDot className="h-3.5 w-3.5 opacity-40" aria-hidden />}
                {STATUS_LABEL[s]}
              </li>
            )
          })}
        </ol>
        {timings && <p className="mt-3 font-mono text-2xs text-slate-500">preprocess {formatDuration(timings.preprocess_s)} &middot; detect {formatDuration(timings.detect_s)} &middot; total {formatDuration(timings.total_s)}</p>}
      </div>

      <div className="min-h-0 p-3">
        <h3 className="label mb-1.5">Quality notes and warnings</h3>
        {reg && reg.reliable && reg.magnitude_px > 1 && <p className="mb-1.5 flex gap-1.5 text-xs text-amber-200"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />Estimated misregistration {reg.magnitude_px.toFixed(1)} px.</p>}
        {issues.length === 0 && !analysis.error && <p className="text-xs text-slate-600">No warnings.</p>}
        <ul className="space-y-1.5">
          {issues.map((w, i) => (
            <li key={`${w.code}-${i}`} className={cn('flex gap-1.5 text-xs', w.level === 'warning' ? 'text-amber-200' : 'text-slate-400')}>
              {w.level === 'warning' ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> : <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}{w.message}
            </li>
          ))}
        </ul>
        <h3 className="label mb-1.5 mt-4">Timeline</h3>
        <ul className="max-h-28 space-y-0.5 overflow-y-auto font-mono text-2xs text-slate-500">
          {events.slice(-12).map((e, i) => <li key={i}><span className="text-slate-600">{formatDate(e.at, { time: true })}</span> {STATUS_LABEL[e.status as keyof typeof STATUS_LABEL] ?? e.status} {e.message ? `- ${e.message}` : ''}</li>)}
        </ul>
      </div>
    </div>
  )
}
