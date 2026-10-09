'use client'

import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { api, ApiError, type AnalyticsAnswer } from '@/lib/api'
import { Button, Chip } from '@/components/ui/kit'
import AnswerCard from './AnswerCard'

/** "Explain this detection": asks the grounded analytics endpoint (measured facts first, optional LLM narration). */
export default function ExplainButton({ analysisId, featureId }: { analysisId: string; featureId: string }) {
  const [answer, setAnswer] = useState<AnalyticsAnswer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true); setError(null)
    try { setAnswer(await api.analytics.query({ spec: { operation: 'explain_feature', feature_id: featureId }, analysis_id: analysisId })) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Analysis failed') } finally { setBusy(false) }
  }
  return (
    <div className="w-full">
      <Button tone="accent" loading={busy} onClick={run}><Sparkles className="h-3.5 w-3.5" aria-hidden /> Explain this change</Button>
      {error && <p role="alert" className="mt-2 text-xs text-red-300">{error}</p>}
      {answer && <div className="mt-2"><AnswerCard answer={answer} compact /><Chip className="mt-1">{answer.answer_source === 'llm_narration' ? 'LLM narration of computed facts' : 'deterministic summary'}</Chip></div>}
    </div>
  )
}
