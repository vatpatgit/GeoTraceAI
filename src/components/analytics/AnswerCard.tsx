'use client'

import { MapPin } from 'lucide-react'
import type { AnalyticsAnswer } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/lib/format'

/** Renders a grounded analytics answer: statement, measured facts, caveats, and clickable references to real detections. */
export default function AnswerCard({ answer, compact = false }: { answer: AnalyticsAnswer; compact?: boolean }) {
  const selectFeature = useAppStore((s) => s.selectFeature)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  return (
    <div className={cn('rounded-md border border-white/[0.08] bg-black/20', compact ? 'p-2.5' : 'p-3.5')}>
      <p className={cn('whitespace-pre-line leading-relaxed text-slate-200', compact ? 'text-xs' : 'text-sm')}>{answer.answer}</p>
      {answer.measured_facts.length > 0 && (
        <ul className="mt-2 space-y-0.5 border-t border-white/[0.06] pt-2 font-mono text-2xs text-slate-400">
          {answer.measured_facts.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
      {answer.caveats.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-2xs text-amber-200/80">{answer.caveats.map((c) => <li key={c}>&bull; {c}</li>)}</ul>
      )}
      {answer.references.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {answer.references.slice(0, 12).map((r) => (
            <button key={`${r.kind}-${r.id}`} className="focus-ring inline-flex items-center gap-1 rounded border border-white/10 px-1.5 py-0.5 text-2xs text-slate-300 hover:border-accent/40 hover:text-accent"
              onClick={() => {
                if (r.kind === 'feature') {
                  if (r.analysis_id && r.analysis_id !== useAppStore.getState().activeAnalysisId) setActive(r.analysis_id)
                  selectFeature(r.id, { fly: true, center: r.centroid ?? undefined })
                } else if (r.kind === 'analysis') setActive(r.id)
              }}>
              <MapPin className="h-3 w-3" aria-hidden />{r.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
