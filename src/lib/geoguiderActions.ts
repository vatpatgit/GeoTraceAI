/**
 * Executes the structured UI instructions GeoGuider returns. Nothing here evaluates text from the backend: every action is checked
 * against an allow-list (route keys, UUIDs, numeric ranges, export paths) first, and an invalid one is dropped.
 */
import { api } from '@/lib/api'
import type { GgAction } from '@/lib/api/geoguider'
import { useAppStore } from '@/store/useAppStore'

export const ROUTE_PATHS: Record<string, string> = {
  dashboard: '/dashboard', map: '/map', analyses: '/analyses', new_analysis: '/analyses/new', regions: '/regions', changes: '/changes',
  alerts: '/alerts', analytics: '/analytics', reports: '/reports', settings: '/settings', image_compare: '/image-compare',
}
const PANELS = ['quick', 'layers'] as const
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const EXPORT_PATH = /^\/(analyses\/[0-9a-f-]{36}\/export\?format=(geojson|gpkg|csv)|reports\/analyses\/[0-9a-f-]{36}\?format=pdf)$/i

const validBbox = (b: unknown): b is [number, number, number, number] =>
  Array.isArray(b) && b.length === 4 && b.every((v) => typeof v === 'number' && Number.isFinite(v)) &&
  b[0] >= -180 && b[2] <= 180 && b[1] >= -90 && b[3] <= 90 && b[0] < b[2] && b[1] < b[3]

export function isValidAction(a: GgAction): boolean {
  switch (a.type) {
    case 'navigate': return a.route in ROUTE_PATHS && (a.panel == null || (PANELS as readonly string[]).includes(a.panel))
    case 'show_aoi': return validBbox(a.bbox)
    case 'open_analysis': return UUID.test(a.analysis_id)
    case 'track_analyses': return a.analysis_ids.length > 0 && a.analysis_ids.length <= 10 && a.analysis_ids.every((i) => UUID.test(i))
    case 'zoom_to': return Array.isArray(a.center) && a.center.length === 2 && a.center.every((v) => Number.isFinite(v)) && Math.abs(a.center[0]) <= 180 && Math.abs(a.center[1]) <= 90
    case 'download_export': return EXPORT_PATH.test(a.path)
    case 'show_weather': case 'start_draw': return true
    default: return false
  }
}

interface Deps { push: (path: string) => void; pathname: string }

export async function runAction(a: GgAction, deps: Deps): Promise<void> {
  if (!isValidAction(a)) return
  const st = useAppStore.getState()
  const ensureMap = () => { if (deps.pathname !== '/map') deps.push('/map') }
  switch (a.type) {
    case 'navigate':
      deps.push(ROUTE_PATHS[a.route])
      if (a.panel) st.setLeftPanel(a.panel as 'quick' | 'layers')
      return
    case 'show_aoi':
      ensureMap()
      st.setDrawnBox(a.bbox as [number, number, number, number])
      st.requestFly({ bbox: a.bbox as [number, number, number, number] })
      return
    case 'open_analysis': {
      const rec = await api.analyses.get(a.analysis_id)
      st.upsertAnalysis(rec)
      ensureMap()
      st.setActiveAnalysis(a.analysis_id)
      return
    }
    case 'track_analyses':
      for (const id of a.analysis_ids) st.upsertAnalysis(await api.analyses.get(id))
      return
    case 'zoom_to':
      ensureMap()
      st.requestFly({ center: [a.center[0], a.center[1]], zoom: 15 })
      return
    case 'show_weather':
      ensureMap()
      st.setLayerVisible('weather-alerts', true)
      st.setLeftPanel('layers')
      return
    case 'start_draw':
      ensureMap()
      st.setLeftPanel('quick')
      st.setDrawMode(true)
      return
    case 'download_export': {
      const { downloadFile } = await import('@/lib/api')
      await downloadFile(a.path, {}, `geotrace.${a.format}`)
      return
    }
  }
}
