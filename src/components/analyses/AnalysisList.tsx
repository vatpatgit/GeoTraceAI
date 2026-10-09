'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api, ApiError, TERMINAL_STATUSES } from '@/lib/api'
import { canWrite } from '@/lib/auth'
import { formatArea, formatDate, formatRelative, STATUS_LABEL } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, DemoBadge, EmptyBlock, ProgressBar } from '@/components/ui/kit'

export default function AnalysisList() {
  const router = useRouter()
  const analyses = useAppStore((s) => s.analyses)
  const setAnalyses = useAppStore((s) => s.setAnalyses)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const setDrawerTab = useAppStore((s) => s.setDrawerTab)
  const user = useAppStore((s) => s.authUser)
  const projects = useAppStore((s) => s.projects)
  const toast = useAppStore((s) => s.toast)
  const [busy, setBusy] = useState<string | null>(null)

  async function remove(id: string) {
    if (!window.confirm('Delete this analysis, its detections and exports? This cannot be undone.')) return
    setBusy(id)
    try { await api.analyses.remove(id); setAnalyses(analyses.filter((a) => a.id !== id)); toast('success', 'Analysis deleted') }
    catch (e) { toast('error', e instanceof ApiError ? e.message : 'Delete failed') } finally { setBusy(null) }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-5">
      <header className="flex items-end justify-between">
        <div><h1 className="text-base font-semibold text-slate-100">Analyses</h1><p className="mt-0.5 text-xs text-slate-500">Every run keeps its imagery provenance, configuration and results.</p></div>
        {canWrite(user?.role) && <Link href="/analyses/new" className="btn border-accent-dim bg-accent-surface text-accent hover:bg-[#1a4430]"><Plus className="h-3.5 w-3.5" aria-hidden /> New analysis</Link>}
      </header>
      {analyses.length === 0 ? <EmptyBlock title="No analyses yet" hint="Upload a before/after GeoTIFF pair or search Sentinel-2 imagery to create the first one." /> : (
        <div className="overflow-hidden rounded-md border border-[color:var(--line-strong)]">
          <table className="w-full text-left text-xs">
            <thead className="bg-ink-850 text-slate-500"><tr className="hairline-b"><th className="label px-3 py-2 font-normal">Name</th><th className="label py-2 font-normal">Status</th><th className="label py-2 font-normal">Dates</th><th className="label py-2 text-right font-normal">Polygons</th><th className="label py-2 text-right font-normal">Changed</th><th className="label py-2 font-normal">Created</th><th /></tr></thead>
            <tbody>
              {analyses.map((a) => (
                <tr key={a.id} className="border-b border-[color:var(--line)] hover:bg-ink-800/70">
                  <td className="px-3 py-2"><button className="focus-ring text-left text-slate-100 hover:text-accent" onClick={() => { setActive(a.id); setDrawerTab(a.status === 'completed' ? 'detections' : 'progress'); router.push('/map') }}>{a.name}</button>
                    <div className="mt-0.5 flex items-center gap-1.5 text-2xs text-slate-500">{projects.find((p) => p.id === a.project_id)?.name}{a.is_demo && <DemoBadge />}<span>{a.method?.replace(/_/g, ' ')}</span></div></td>
                  <td className="py-2"><Chip tone={a.status === 'failed' ? 'danger' : a.status === 'completed' ? 'ok' : a.status === 'cancelled' ? 'default' : 'accent'}>{STATUS_LABEL[a.status]}</Chip>{!TERMINAL_STATUSES.includes(a.status) && <ProgressBar value={a.progress} className="mt-1 w-24" />}</td>
                  <td className="py-2 font-mono text-2xs text-slate-400">{formatDate(a.before_date)} &rarr; {formatDate(a.after_date)}</td>
                  <td className="py-2 text-right font-mono text-slate-200">{a.summary?.feature_count ?? '-'}</td>
                  <td className="py-2 text-right font-mono text-slate-200">{a.summary ? formatArea(a.summary.total_changed_area_m2) : '-'}</td>
                  <td className="py-2 text-2xs text-slate-500">{formatRelative(a.created_at)}</td>
                  <td className="py-2 pr-2 text-right">{canWrite(user?.role) && TERMINAL_STATUSES.includes(a.status) && <Button tone="ghost" aria-label={`Delete ${a.name}`} loading={busy === a.id} onClick={() => remove(a.id)}><Trash2 className="h-3.5 w-3.5" aria-hidden /></Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
