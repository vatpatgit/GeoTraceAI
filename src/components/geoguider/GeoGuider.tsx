'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Compass, Plus, Send, X } from 'lucide-react'
import type { GgAction, GgUi } from '@/lib/api/geoguider'
import { runAction } from '@/lib/geoguiderActions'
import { cn } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { useGeoGuider, WELCOME } from '@/store/useGeoGuider'
import { Block, type BlockCtx } from './Blocks'

const STARTERS = [
  { text: 'Show me changes in Mumbai over the past 10 years.', needs: 'change_detection' },
  { text: 'Compare two satellite images of this area.', needs: 'change_detection' },
  { text: 'Find recent Sentinel-2 imagery for my selected AOI.', needs: 'change_detection' },
  { text: 'Analyze changes around this location between two dates.', needs: 'change_detection' },
  { text: 'Show available weather alerts for this region.', needs: 'weather_alerts' },
  { text: 'Explain the changes detected on the map.', needs: 'results' },
  { text: 'Export the current change-detection results.', needs: 'results' },
]

export default function GeoGuider() {
  const s = useGeoGuider()
  const router = useRouter()
  const pathname = usePathname()
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const toast = useAppStore((a) => a.toast)

  const ui = useCallback((): GgUi => {
    const st = useAppStore.getState()
    return { page: pathname, active_analysis_id: st.activeAnalysisId, drawn_bbox: st.drawnBox ?? null }
  }, [pathname])

  const exec = useCallback(async (actions: GgAction[]) => {
    for (const a of actions) {
      try { await runAction(a, { push: router.push, pathname }) } catch (e) { toast('error', e instanceof Error ? e.message : 'Could not complete that action.') }
    }
  }, [router.push, pathname, toast])

  useEffect(() => { void s.loadStatus(); void s.restore() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (s.open) inputRef.current?.focus() }, [s.open])
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }) }, [s.messages.length, s.busy, s.open])

  // Live job state: poll only while a job is really running; the backend advances the workflow from the job rows.
  const running = s.workflow?.state === 'PREPROCESSING' || s.workflow?.state === 'ANALYZING'
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => { void s.poll().then(exec) }, 4000)
    return () => clearInterval(t)
  }, [running]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (text: string) => {
    if (!text.trim() || s.busy) return
    setDraft('')
    await exec(await s.send(text, ui()))
  }
  const ctx: BlockCtx = {
    workflow: s.workflow, busy: s.busy,
    onChoose: (p, o) => { void s.choose(p, o, ui()).then(exec) },
    onAction: (a) => { void exec([a]) },
    onRetry: () => { void s.retry().then(exec) },
    onCancel: () => { void s.cancel().then(exec) },
  }
  const caps = s.status?.capabilities
  const starters = STARTERS.filter((x) => !caps || caps[x.needs] !== false || x.needs === 'results')
  const lastAssistant = [...s.messages].reverse().find((m) => m.role === 'assistant')

  if (!s.open) {
    return (
      <button ref={launcherRef} onClick={() => s.setOpen(true)} aria-label="Open GeoGuider assistant" title="GeoGuider: AI geospatial copilot"
        className="focus-ring fixed bottom-4 right-4 z-[60] flex items-center gap-2 rounded-full border border-accent/40 bg-ink-900 px-3.5 py-2.5 text-xs font-medium text-accent shadow-xl shadow-black/60 hover:bg-accent/10">
        <Compass className="h-4 w-4" aria-hidden /> GeoGuider
        {running && <span className="h-2 w-2 animate-pulse rounded-full bg-accent" aria-label="An analysis is running" />}
      </button>
    )
  }

  return (
    <section role="dialog" aria-label="GeoGuider assistant" onKeyDown={(e) => { if (e.key === 'Escape') { s.setOpen(false); launcherRef.current?.focus() } }}
      className="panel-solid fixed bottom-4 right-4 z-[60] flex h-[min(680px,calc(100vh-2rem))] w-[420px] max-w-[calc(100vw-2rem)] flex-col rounded-lg shadow-2xl shadow-black/70 max-sm:inset-x-2 max-sm:bottom-2 max-sm:w-auto max-sm:max-w-none">
      <header className="flex items-center gap-2 border-b border-white/[0.06] px-3 py-2">
        <Compass className="h-4 w-4 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-slate-100">GeoGuider</h2>
          <p className="truncate text-2xs text-slate-500">{s.status ? (s.status.llm.configured ? `Language model: ${s.status.llm.provider}` : 'Built-in command parser (no LLM configured)') : 'Connecting…'}</p>
        </div>
        <button className="focus-ring rounded p-1 text-slate-400 hover:text-slate-100" aria-label="New conversation" title="New conversation" onClick={() => s.reset()}><Plus className="h-4 w-4" /></button>
        <button className="focus-ring rounded p-1 text-slate-400 hover:text-slate-100" aria-label="Close GeoGuider" onClick={() => { s.setOpen(false); launcherRef.current?.focus() }}><X className="h-4 w-4" /></button>
      </header>

      <div role="log" aria-live="polite" aria-label="Conversation" className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        <div className="max-w-[92%] rounded-lg rounded-tl-sm bg-white/[0.05] px-3 py-2 text-xs leading-relaxed text-slate-200">{WELCOME}</div>
        {s.status && !s.status.llm.configured && s.status.llm.note && <p className="rounded-md border border-amber-400/20 bg-amber-400/[0.05] px-2.5 py-1.5 text-2xs text-amber-200">{s.status.llm.note}</p>}
        {s.messages.length === 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Suggested prompts">
            {starters.map((x) => <button key={x.text} onClick={() => void submit(x.text)} className="focus-ring rounded-full border border-white/10 px-2.5 py-1 text-2xs text-slate-300 hover:border-accent/40 hover:text-accent">{x.text}</button>)}
          </div>
        )}
        {s.messages.map((m) => (
          <div key={m.id} className={cn('flex flex-col gap-1.5', m.role === 'user' && 'items-end')}>
            <div className={cn('max-w-[92%] whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-xs leading-relaxed', m.role === 'user' ? 'rounded-tr-sm bg-accent/15 text-slate-100' : 'rounded-tl-sm bg-white/[0.05] text-slate-200')}>
              <Rich text={m.content} />
            </div>
            {m.blocks.length > 0 && <div className="w-full space-y-1.5">{m.blocks.map((b, i) => <Block key={i} b={b} ctx={ctx} current={m.id === lastAssistant?.id} />)}</div>}
          </div>
        ))}
        {s.busy && <div className="flex items-center gap-2 text-2xs text-slate-500" role="status"><span className="flex gap-0.5"><i className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500" /><i className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500 [animation-delay:120ms]" /><i className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500 [animation-delay:240ms]" /></span> Working… searching real services (or a local language model) can take a minute or more.</div>}
        {s.error && <div role="alert" className="flex items-center justify-between gap-2 rounded-md border border-red-500/30 bg-red-500/[0.06] px-2.5 py-1.5 text-2xs text-red-200"><span>{s.error}</span><button className="btn" onClick={() => void s.retry().then(exec)}>Retry</button></div>}
        <div ref={endRef} />
      </div>

      {s.suggestions.length > 0 && !s.busy && (
        <div className="flex flex-wrap gap-1.5 border-t border-white/[0.06] px-3 py-2" aria-label="Suggested follow-ups">
          {s.suggestions.map((t) => <button key={t} onClick={() => void submit(t)} className="focus-ring rounded-full border border-white/10 px-2.5 py-0.5 text-2xs text-slate-300 hover:border-accent/40 hover:text-accent">{t}</button>)}
        </div>
      )}
      <form className="flex items-end gap-2 border-t border-white/[0.06] p-2.5" onSubmit={(e) => { e.preventDefault(); void submit(draft) }}>
        <label htmlFor="geoguider-input" className="sr-only">Message GeoGuider</label>
        <textarea id="geoguider-input" ref={inputRef} value={draft} rows={1} maxLength={1000} placeholder="Ask about an area, a period, or your results…"
          onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(draft) } }}
          className="focus-ring max-h-28 min-h-[2.25rem] flex-1 resize-none rounded-md border border-white/10 bg-black/30 px-2.5 py-2 text-xs text-slate-100 placeholder:text-slate-600" />
        <button type="submit" disabled={s.busy || !draft.trim()} aria-label="Send message" className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-md border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40"><Send className="h-4 w-4" /></button>
      </form>
    </section>
  )
}

/** Minimal inline formatting: **bold** only. Message text is plain text, never HTML. */
function Rich({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith('**') && p.endsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>))}</>
}
