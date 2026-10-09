import type { Map as MlMap } from 'maplibre-gl'
import type { WeatherAlert } from '@/lib/api/weather'
import { weatherFeatureCollection } from '@/lib/weather'

const SRC = 'weather-alerts'
export const WEATHER_FILL = 'weather-alerts-fill'
const IDS = [WEATHER_FILL, 'weather-alerts-line', 'weather-alerts-point']

/** Provider weather-alert areas: dashed outlines + translucent fill, severity coloured. Separate from imagery and change-detection layers. */
export function syncWeather(map: MlMap, alerts: WeatherAlert[], visible: boolean, opacity: number, selectedId: string | null): void {
  const fc = weatherFeatureCollection(alerts, selectedId)
  if (!visible || fc.features.length === 0) {
    for (const l of IDS) if (map.getLayer(l)) map.removeLayer(l)
    if (map.getSource(SRC)) map.removeSource(SRC)
    return
  }
  const src = map.getSource(SRC) as import('maplibre-gl').GeoJSONSource | undefined
  if (src) src.setData(fc as unknown as GeoJSON.FeatureCollection)
  else {
    map.addSource(SRC, { type: 'geojson', data: fc as unknown as GeoJSON.FeatureCollection })
    map.addLayer({ id: WEATHER_FILL, type: 'fill', source: SRC, filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.3 } })
    map.addLayer({ id: 'weather-alerts-line', type: 'line', source: SRC, filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['==', ['get', 'selected'], 1], 4, 2], 'line-dasharray': [2, 1.5] } })
    map.addLayer({ id: 'weather-alerts-point', type: 'circle', source: SRC, filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': 9, 'circle-color': ['get', 'color'], 'circle-stroke-color': '#fff', 'circle-stroke-width': ['case', ['==', ['get', 'selected'], 1], 3, 1.5] } })
  }
  map.setPaintProperty(WEATHER_FILL, 'fill-opacity', Math.max(0, Math.min(1, opacity * 0.7)))
}
