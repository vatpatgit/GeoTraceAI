import type { Map as MlMap } from 'maplibre-gl'
import type { QuickCompare } from '@/store/useAppStore'

const ID = 'quick-image'

/** Draw (or clear) the retrieved Sentinel-2 image for this map role. before-map -> before image; every other role -> after image. */
export function syncQuickImage(map: MlMap, qc: QuickCompare | null, role: 'before' | 'after' | 'single'): void {
  const scene = qc ? (role === 'before' ? qc.before : qc.after) : null
  const src = map.getSource(ID) as (import('maplibre-gl').ImageSource & { __url?: string }) | undefined
  if (!scene || !qc) {
    if (map.getLayer(ID)) map.removeLayer(ID)
    if (src) map.removeSource(ID)
    return
  }
  if (src && src.__url === scene.url) return
  if (map.getLayer(ID)) map.removeLayer(ID)
  if (src) map.removeSource(ID)
  const [w, s, e, n] = qc.bbox
  map.addSource(ID, { type: 'image', url: scene.url, coordinates: [[w, n], [e, n], [e, s], [w, s]] })
  ;(map.getSource(ID) as unknown as { __url?: string }).__url = scene.url
  map.addLayer({ id: ID, type: 'raster', source: ID, paint: { 'raster-opacity': 1, 'raster-fade-duration': 0 } }, map.getLayer('regions-fill') ? 'regions-fill' : undefined)
}

const SRC = 'quick-changes'

/** Highlight ML-detected change polygons (after-side maps only). */
export function syncQuickChanges(map: MlMap, fc: { features: unknown[] } | null, show: boolean, role: 'before' | 'after' | 'single'): void {
  const want = show && !!fc && role !== 'before'
  const src = map.getSource(SRC) as import('maplibre-gl').GeoJSONSource | undefined
  if (!want) {
    for (const l of ['quick-changes-line', 'quick-changes-fill']) if (map.getLayer(l)) map.removeLayer(l)
    if (src) map.removeSource(SRC)
    return
  }
  const data = { type: 'FeatureCollection', features: fc!.features } as unknown as GeoJSON.FeatureCollection
  if (src) { src.setData(data); return }
  map.addSource(SRC, { type: 'geojson', data })
  map.addLayer({ id: 'quick-changes-fill', type: 'fill', source: SRC, paint: { 'fill-color': '#F43F5E', 'fill-opacity': 0.5 } })
  map.addLayer({ id: 'quick-changes-line', type: 'line', source: SRC, paint: { 'line-color': '#FDE047', 'line-width': 2.5 } })
}
