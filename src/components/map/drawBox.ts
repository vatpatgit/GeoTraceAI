import type { Map as MlMap } from 'maplibre-gl'
import type { BBox } from '@/lib/api'

const SRC = 'draw-box'
const FILL = 'draw-box-fill'
const LINE = 'draw-box-line'

export const boxFromCorners = (a: [number, number], b: [number, number]): BBox => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]

export const boxPolygon = (b: BBox) => ({
  type: 'Feature' as const, properties: {},
  geometry: { type: 'Polygon' as const, coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] },
})

/** Approximate size of a lon/lat box in km (width at the middle latitude, height). */
export function boxSizeKm(b: BBox): { w: number; h: number } {
  const lat = ((b[1] + b[3]) / 2) * (Math.PI / 180)
  return { w: (b[2] - b[0]) * 111.32 * Math.cos(lat), h: (b[3] - b[1]) * 110.57 }
}

/** Show (or clear) a rectangle on a MapLibre map. */
export function syncDrawBox(map: MlMap, box: BBox | null): void {
  const src = map.getSource(SRC) as import('maplibre-gl').GeoJSONSource | undefined
  if (!box) {
    for (const l of [LINE, FILL]) if (map.getLayer(l)) map.removeLayer(l)
    if (src) map.removeSource(SRC)
    return
  }
  const data = boxPolygon(box) as unknown as GeoJSON.Feature
  if (src) { src.setData(data); return }
  map.addSource(SRC, { type: 'geojson', data })
  map.addLayer({ id: FILL, type: 'fill', source: SRC, paint: { 'fill-color': '#22D3EE', 'fill-opacity': 0.14 } })
  map.addLayer({ id: LINE, type: 'line', source: SRC, paint: { 'line-color': '#22D3EE', 'line-width': 2, 'line-dasharray': [3, 2] } })
}
