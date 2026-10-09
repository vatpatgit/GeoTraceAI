import type { WeatherAlert, WeatherSeverity } from '@/lib/api/weather'
import { formatDate } from '@/lib/format'

/** Severity -> colour. Colour is never the only signal: the UI always pairs it with the severity word and an icon shape. */
export const WEATHER_COLOR: Record<WeatherSeverity, string> = { unknown: '#94A3B8', minor: '#38BDF8', moderate: '#FBBF24', severe: '#FB923C', extreme: '#EF4444' }
export const WEATHER_RANK: Record<WeatherSeverity, number> = { unknown: 0, minor: 1, moderate: 2, severe: 3, extreme: 4 }
export const TAG_LABEL = (t: string): string => t.replace(/_/g, ' ')

export function alertWindow(a: Pick<WeatherAlert, 'start_time' | 'end_time'>): string {
  if (!a.start_time && !a.end_time) return 'Time not provided'
  const f = (v: string | null) => (v ? formatDate(v, { time: true }) : '?')
  return `${f(a.start_time)} → ${f(a.end_time)}`
}

export function geometryBBox(g: unknown): [number, number, number, number] | null {
  const pts: number[][] = []
  const walk = (c: unknown): void => { if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[]); else if (Array.isArray(c)) c.forEach(walk) }
  walk((g as { coordinates?: unknown } | null)?.coordinates)
  if (!pts.length) return null
  const xs = pts.map((p) => p[0]); const ys = pts.map((p) => p[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]
}

/** FeatureCollection for the map layers (only alerts that carry geometry; `severity` / `selected` drive styling). */
export function weatherFeatureCollection(alerts: WeatherAlert[], selectedId: string | null) {
  return {
    type: 'FeatureCollection' as const,
    features: alerts.filter((a) => a.geometry && a.status === 'active').map((a) => ({
      type: 'Feature' as const, id: a.id, geometry: a.geometry,
      properties: { id: a.id, title: a.title, severity: a.severity, color: WEATHER_COLOR[a.severity], selected: a.id === selectedId ? 1 : 0 },
    })),
  }
}
