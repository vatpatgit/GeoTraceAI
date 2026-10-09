'use client'

import { useEffect, useRef } from 'react'
import { AlertTriangle, ExternalLink, Info, X } from 'lucide-react'
import type { LayerInfo } from '@/lib/api'
import { cn, formatDate } from '@/lib/format'
import { CHANGE_LAYERS, selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { effectiveAvailability } from '@/lib/layers/env'
import { Chip, Spinner, Switch } from '@/components/ui/kit'

const AVAIL: Record<LayerInfo['availability'], { label: string; tone: 'ok' | 'warn' | 'danger' | 'default' }> = {
  available: { label: 'available', tone: 'ok' },
  unknown: { label: 'unchecked', tone: 'default' },
  unavailable: { label: 'unavailable', tone: 'danger' },
  needs_credentials: { label: 'needs credentials', tone: 'warn' },
  requires_analysis: { label: 'needs analysis', tone: 'warn' },
}

function Legend({ l }: { l: LayerInfo }) {
  const lg = l.legend
  if (!lg) return null
  if (lg.kind === 'gradient' && lg.stops?.length) {
    const grad = `linear-gradient(90deg, ${lg.stops.map((s) => s.color).join(', ')})`
    return (
      <div className="mt-1.5">
        <div className="h-1.5 rounded-full" style={{ background: grad }} aria-hidden />
        <div className="mt-0.5 flex justify-between font-mono text-2xs text-slate-500"><span>{lg.stops[0].value}</span><span>{lg.unit}</span><span>{lg.stops[lg.stops.length - 1].value}</span></div>
      </div>
    )
  }
  return (
    <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
      {lg.stops?.map((s) => <li key={s.value} className="flex items-center gap-1 text-2xs text-slate-400"><span className="h-2 w-2 rounded-sm" style={{ background: s.color }} aria-hidden />{s.value}</li>)}
    </ul>
  )
}

function Row({ id, name, description, info, hint }: { id: string; name: string; description?: string; info?: LayerInfo; hint?: string }) {
  const analysis = useAppStore(selectActiveAnalysis)
  const avail = info ? effectiveAvailability(info, analysis) : null
  const st = useAppStore((s) => s.layerState[id])
  const setVisible = useAppStore((s) => s.setLayerVisible)
  const setOpacity = useAppStore((s) => s.setLayerOpacity)
  const disabled = avail ? (avail === 'unavailable' || avail === 'needs_credentials' || avail === 'requires_analysis') : false
  const visible = !!st?.visible
  const status = avail ? AVAIL[avail] : null
  return (
    <li className="hairline-b px-3 py-2 last:border-b-0">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className={cn('truncate text-xs', visible ? 'text-slate-100' : 'text-slate-300')}>{name}</span>
            {st?.loading && <Spinner className="h-3 w-3" />}
            {status && avail !== 'available' && <Chip tone={status.tone}>{status.label}</Chip>}
          </div>
          {(description || hint) && <p className="mt-0.5 text-2xs text-slate-500">{hint ?? description}</p>}
        </div>
        <Switch checked={visible} disabled={disabled} onChange={(v) => setVisible(id, v)} label={`Toggle ${name}`} />
      </div>
      {st?.error && <p role="alert" className="mt-1 flex items-center gap-1 text-2xs text-amber-300"><AlertTriangle className="h-3 w-3" aria-hidden />{st.error}</p>}
      {visible && (
        <div className="mt-1.5 space-y-1">
          <label className="flex items-center gap-2 text-2xs text-slate-500">
            <span className="w-12 shrink-0">Opacity</span>
            <input type="range" min={0} max={1} step={0.05} value={st?.opacity ?? 1} onChange={(e) => setOpacity(id, Number(e.target.value))} aria-label={`${name} opacity`} className="h-1 flex-1" />
            <span className="w-8 text-right font-mono">{Math.round((st?.opacity ?? 1) * 100)}%</span>
          </label>
          {info && <Legend l={info} />}
        </div>
      )}
      {info && (
        <details className="mt-1.5 text-2xs text-slate-500">
          <summary className="flex cursor-pointer select-none items-center gap-1 hover:text-slate-300"><Info className="h-3 w-3" aria-hidden /> Source and limitations</summary>
          <div className="mt-1 space-y-1 pl-4">
            <p><span className="text-slate-400">Provider:</span> {info.provider} ({info.data_type})</p>
            {info.temporal && <p><span className="text-slate-400">Time:</span> {info.temporal.kind}{info.temporal.default_time ? `, ${info.temporal.default_time}` : ''}{info.last_updated_at ? `, updated ${formatDate(info.last_updated_at)}` : ''}</p>}
            {info.availability_detail && <p><span className="text-slate-400">Status:</span> {info.availability_detail}</p>}
            <p><span className="text-slate-400">Attribution:</span> {info.attribution.replace(/<[^>]+>/g, '')}</p>
            {info.limitations.length > 0 && <ul className="list-disc pl-4 text-amber-200/70">{info.limitations.map((x) => <li key={x}>{x}</li>)}</ul>}
          </div>
        </details>
      )}
    </li>
  )
}

export default function LayerPanel() {
  const catalog = useAppStore((s) => s.layerCatalog)
  const analysis = useAppStore(selectActiveAnalysis)
  const setLeftPanel = useAppStore((s) => s.setLeftPanel)
  const focus = useAppStore((s) => s.layerFocus)
  const envRef = useRef<HTMLDivElement>(null)
  const riskRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = focus === 'risk' ? riskRef.current : focus === 'environmental' ? envRef.current : null
    el?.scrollIntoView({ block: 'start' })
  }, [focus])

  const env = catalog.filter((l) => l.group === 'environmental')
  const risk = catalog.filter((l) => l.group === 'risk')
  const hasAnalysis = analysis?.status === 'completed'
  const hasNdvi = !!analysis?.processing?.grid?.roles?.includes('nir') && !!analysis?.processing?.grid?.roles?.includes('red')

  return (
    <aside aria-label="Layers" className="panel absolute bottom-9 left-14 top-3 z-20 flex w-72 flex-col rounded-md shadow-2xl shadow-black/50">
      <header className="hairline-b flex items-center justify-between px-3 py-2">
        <h2 className="label">Layers</h2>
        <button onClick={() => setLeftPanel(null)} aria-label="Close layers panel" className="focus-ring rounded text-slate-500 hover:text-slate-200"><X className="h-3.5 w-3.5" /></button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="label px-3 pb-1 pt-3">Change intelligence</div>
        <ul>
          {CHANGE_LAYERS.map((l) => {
            const unavailable = (l.id.startsWith('imagery') || l.id === 'change-score') && !hasAnalysis
            const needsNdvi = l.id === 'delta-ndvi' && hasAnalysis && !hasNdvi
            return <Row key={l.id} id={l.id} name={l.name} description={l.description}
              hint={unavailable ? 'Select a completed analysis' : needsNdvi ? 'Needs red + NIR bands in the imagery' : undefined} />
          })}
        </ul>

        <div ref={envRef} className="label px-3 pb-1 pt-4">Environmental</div>
        {env.length ? <ul>{env.map((l) => <Row key={l.id} id={l.id} name={l.name} info={l} />)}</ul> : <p className="px-3 pb-2 text-2xs text-slate-600">Layer catalogue not loaded.</p>}

        <div ref={riskRef} className="label px-3 pb-1 pt-4">Risk assessment</div>
        {risk.length ? <ul>{risk.map((l) => <Row key={l.id} id={l.id} name={l.name} info={l} />)}</ul> : <p className="px-3 pb-2 text-2xs text-slate-600">Layer catalogue not loaded.</p>}
        <p className="flex items-start gap-1.5 px-3 py-3 text-2xs text-slate-600"><ExternalLink className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />Global layers are third-party observations at coarse resolution. They are context, not part of the change detection.</p>
      </div>
    </aside>
  )
}
