'use client'

import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Send } from 'lucide-react'
import { api, ApiError, SEVERITIES, type AnalyticsAnswer } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { categoryLabel, formatArea, formatDate, SEVERITY_COLOR } from '@/lib/format'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import AnswerCard from '@/components/analytics/AnswerCard'
import { Button, Chip, DemoBadge, EmptyBlock, ErrorBlock, inputCls, Skeleton } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'

interface Series { analysis_id: string; name: string; date: string; changed_area_m2: number | null; feature_count: number | null; analyzed_area_m2: number | null; is_demo: boolean }

const AXIS = { fill: '#94a3b8', fontSize: 11 }
const TIP = { background: '#101913', border: '1px solid rgba(255,255,255,0.1)', fontSize: 12 }

export default function AnalyticsPage() {
  const analyses = useAppStore((s) => s.analyses).filter((a) => a.status === 'completed')
  const active = useAppStore(selectActiveAnalysis)
  const [pick, setPick] = useState<string | null>(null)
  const current = analyses.find((a) => a.id === (pick ?? active?.id)) ?? analyses[0] ?? null
  const [q, setQ] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<{ q: string; a: AnalyticsAnswer }[]>([])
  const projectId = current?.project_id
  const ov = useAsync(() => api.analytics.overview({ project_id: projectId }) as Promise<unknown> as Promise<{ series: Series[] }>, [projectId])
  const suggestions = answers[0]?.a.suggestions.length ? answers[0].a.suggestions : [
    'What changed between the selected dates?', 'Which are the 5 largest changes?', 'Which detections require human review?', 'How much vegetation changed?', 'Compare this analysis with the previous run',
  ]

  async function ask(text: string) {
    const question = text.trim()
    if (!question || asking) return
    setAsking(true); setError(null)
    try {
      const a = await api.analytics.query({ question, analysis_id: current?.id, project_id: current?.project_id })
      setAnswers((prev) => [{ q: question, a }, ...prev]); setQ('')
    } catch (e) { setError(e instanceof ApiError ? e.message : 'The question could not be answered.') } finally { setAsking(false) }
  }

  const series = (ov.data?.series ?? []).filter((s) => s.changed_area_m2 != null).map((s) => ({ ...s, label: formatDate(s.date), hectares: (s.changed_area_m2 ?? 0) / 10_000 }))
  const sev = current?.summary ? SEVERITIES.map((s) => ({ severity: s, polygons: current.summary!.by_severity[s] ?? 0 })) : []
  const cat = current?.summary ? Object.entries(current.summary.area_by_category_m2).map(([c, m2]) => ({ category: categoryLabel(c), hectares: m2 / 10_000 })) : []

  return (
    <PageFrame wide title="Analytics" subtitle="Questions are mapped to a fixed set of query operations and answered from stored results. Nothing is estimated beyond what the detections contain.">
      {analyses.length === 0 ? <Card><EmptyBlock title="No completed analyses" hint="Analytics need at least one completed analysis." /></Card> : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <label htmlFor="an-pick" className="label">Analysis</label>
            <select id="an-pick" className={`${inputCls} max-w-md`} value={current?.id ?? ''} onChange={(e) => setPick(e.target.value)}>
              {analyses.map((a) => <option key={a.id} value={a.id}>{a.name} · {formatDate(a.after_date)}</option>)}
            </select>
            {current?.is_demo && <DemoBadge />}
            {current?.model_id && <Chip tone="warn" title="Model scores are uncalibrated and not probabilities.">model score uncalibrated</Chip>}
          </div>

          <Card title="Ask about this analysis">
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void ask(q) }}>
              <input aria-label="Ask a question" className={inputCls} value={q} maxLength={500} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Which are the 5 largest changes?" />
              <Button type="submit" tone="accent" loading={asking} disabled={!q.trim()}><Send className="h-3.5 w-3.5" aria-hidden /> Ask</Button>
            </form>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {suggestions.map((s) => <button key={s} onClick={() => void ask(s)} disabled={asking} className="focus-ring rounded border border-[color:var(--line-strong)] px-2 py-0.5 text-2xs text-slate-400 hover:border-accent-dim hover:text-accent disabled:opacity-40">{s}</button>)}
            </div>
            {error && <ErrorBlock message={error} />}
            <div className="mt-3 space-y-3">
              {answers.map(({ q: question, a }, i) => (
                <div key={`${i}-${question}`}>
                  <div className="mb-1 flex items-center gap-2 text-2xs text-slate-500"><span className="font-mono">Q:</span> {question}
                    {a.understood && <Chip title="The approved operation your question was mapped to">{a.operation.replace(/_/g, ' ')}</Chip>}
                    {a.answer_source === 'llm_narration' && <Chip tone="accent" title="Wording by a language model; every figure was checked against the computed facts.">LLM wording, figures verified</Chip>}</div>
                  {a.understood ? <AnswerCard answer={a} /> : (
                    <div className="rounded-md border border-[color:var(--line-strong)] bg-black/20 p-3 text-xs text-slate-300">{a.answer}</div>
                  )}
                </div>
              ))}
              {answers.length === 0 && <p className="text-xs2 text-slate-500">No questions yet. Answers list their measured facts and link to the detections they refer to.</p>}
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Polygons by severity (heuristic tier)">
              {current?.summary && current.summary.feature_count > 0 ? (
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={sev} margin={{ left: -16, right: 4, top: 4 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis dataKey="severity" tick={AXIS} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ ...AXIS, fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={TIP} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                    <Bar dataKey="polygons" fill="#6EE7A0" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyBlock title="No detections in this analysis" />}
              <ul className="mt-2 flex flex-wrap gap-3 text-2xs text-slate-500">{SEVERITIES.map((s) => <li key={s} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: SEVERITY_COLOR[s] }} />{s}: {current?.summary?.by_severity[s] ?? 0}</li>)}</ul>
            </Card>
            <Card title="Changed area by category (hectares)">
              {cat.length ? (
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={cat} layout="vertical" margin={{ left: 20, right: 12, top: 4 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" horizontal={false} />
                    <XAxis type="number" tick={{ ...AXIS, fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="category" width={130} tick={AXIS} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={TIP} cursor={{ fill: 'rgba(255,255,255,0.04)' }} formatter={(v: number) => `${v.toFixed(2)} ha`} />
                    <Bar dataKey="hectares" fill="#6EE7A0" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyBlock title="No category areas" />}
              <p className="mt-2 text-2xs text-slate-500">Categories are inferred (spectral index or model), not field-verified. Total {formatArea(current?.summary?.total_changed_area_m2)}.</p>
            </Card>
          </div>

          <Card title="Changed area per analysis over time (hectares)">
            {ov.loading && !ov.data ? <Skeleton className="h-40" /> : ov.error ? <ErrorBlock message={ov.error} onRetry={ov.reload} /> : series.length < 2 ? (
              <EmptyBlock title="Not enough history for a trend" hint="A trend needs at least two completed analyses of the same project. GeoTrace does not extrapolate from a single run." />
            ) : (
              <ResponsiveContainer width="100%" height={210}>
                <LineChart data={series} margin={{ left: -8, right: 12, top: 8 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
                  <YAxis tick={{ ...AXIS, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={TIP} formatter={(v: number) => `${v.toFixed(2)} ha`} labelFormatter={(l, p) => `${p?.[0]?.payload?.name ?? ''} · ${l}`} />
                  <Line type="monotone" dataKey="hectares" stroke="#6EE7A0" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
            <p className="mt-1 text-2xs text-slate-500">Points are different image pairs (and possibly different areas or methods) — compare with care.</p>
          </Card>
        </>
      )}
    </PageFrame>
  )
}
