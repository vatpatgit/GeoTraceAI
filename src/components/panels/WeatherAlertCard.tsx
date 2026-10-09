'use client'

import { X } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { SeverityTag, WeatherAlertDetails } from '@/components/pages/WeatherAlertsSection'
import { TAG_LABEL } from '@/lib/weather'
import { Chip } from '@/components/ui/kit'

/** Details of the selected provider weather alert (kept visually and semantically apart from change-detection details). */
export default function WeatherAlertCard() {
  const id = useAppStore((s) => s.selectedWeatherId)
  const a = useAppStore((s) => s.weatherAlerts.find((x) => x.id === id) ?? null)
  const select = useAppStore((s) => s.selectWeather)
  if (!a) return null
  return (
    <aside aria-label="Selected weather alert" className="panel absolute bottom-12 right-3 z-30 max-h-[55%] w-[22rem] overflow-y-auto rounded-md p-3 shadow-2xl shadow-black/50">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="label">Weather alert (OpenWeather)</div>
          <h3 className="mt-0.5 text-sm font-medium text-slate-100">{a.title}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5"><SeverityTag severity={a.severity} />{a.tags.map((t) => <Chip key={t}>{TAG_LABEL(t)}</Chip>)}</div>
        </div>
        <button onClick={() => select(null)} aria-label="Close weather alert details" className="focus-ring rounded text-slate-500 hover:text-slate-200"><X className="h-3.5 w-3.5" /></button>
      </header>
      {a.description && <p className="mt-2 text-xs text-slate-300">{a.description}</p>}
      <div className="mt-2"><WeatherAlertDetails a={a} /></div>
      <p className="mt-2 text-2xs text-amber-200/80">The outlined area is provided by the weather service. It is not derived from satellite imagery and does not show where damage occurred.</p>
    </aside>
  )
}
