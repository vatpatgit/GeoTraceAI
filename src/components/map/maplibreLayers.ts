import type { GeoJSONSource, Map as MlMap, RasterLayerSpecification } from 'maplibre-gl'
import type { BBox, FeatureCollectionLite, LayerInfo, Region } from '@/lib/api'
import { analysisTileUrl, authHeaders, isApiTileUrl } from '@/lib/api'
import type { LayerState } from '@/store/useAppStore'
import { SEVERITY_COLOR } from '@/lib/format'

export type MapRole = 'single' | 'before' | 'after'

export const SEVERITY_MATCH: unknown[] = [
  'match', ['get', 'severity'],
  'critical', SEVERITY_COLOR.critical, 'high', SEVERITY_COLOR.high, 'medium', SEVERITY_COLOR.medium, SEVERITY_COLOR.low,
]

/** MapLibre `transformRequest`: attach the bearer token to access-controlled API tile requests only. */
export function transformRequest(url: string): { url: string; headers?: Record<string, string> } {
  return isApiTileUrl(url) ? { url, headers: authHeaders() } : { url }
}

// Draw order, bottom -> top. Environmental layers are inserted below the first of these that exists.
const ORDER = [
  'imagery-before', 'imagery-after', 'change-score', 'delta-ndvi',
  'aoi-fill', 'aoi-line', 'regions-fill', 'regions-line',
  'features-fill', 'features-line', 'features-hover', 'features-selected',
] as const

function beforeIdFor(map: MlMap, id: string): string | undefined {
  const idx = ORDER.indexOf(id as (typeof ORDER)[number])
  const from = idx === -1 ? 0 : idx + 1
  for (let i = from; i < ORDER.length; i++) if (map.getLayer(ORDER[i])) return ORDER[i]
  return undefined
}

interface UrlMap { [sourceId: string]: string }
const urls = new WeakMap<MlMap, UrlMap>()

function ensureRaster(map: MlMap, id: string, tileUrl: string, opacity: number, visible: boolean, maxzoom = 22) {
  const known = urls.get(map) ?? {}
  urls.set(map, known)
  if (known[id] !== undefined && known[id] !== tileUrl) {
    if (map.getLayer(id)) map.removeLayer(id)
    if (map.getSource(id)) map.removeSource(id)
    delete known[id]
  }
  if (!map.getSource(id)) {
    map.addSource(id, { type: 'raster', tiles: [tileUrl], tileSize: 256, maxzoom })
    known[id] = tileUrl
  }
  if (!map.getLayer(id)) {
    const spec: RasterLayerSpecification = { id, type: 'raster', source: id, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 }, layout: { visibility: visible ? 'visible' : 'none' } }
    map.addLayer(spec, beforeIdFor(map, id) ?? firstOrderedLayer(map))
  } else {
    map.setPaintProperty(id, 'raster-opacity', opacity)
    map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
  }
}

function firstOrderedLayer(map: MlMap): string | undefined {
  for (const id of ORDER) if (map.getLayer(id)) return id
  return undefined
}

function removeRaster(map: MlMap, id: string) {
  if (map.getLayer(id)) map.removeLayer(id)
  if (map.getSource(id)) map.removeSource(id)
  const known = urls.get(map)
  if (known) delete known[id]
}

function boundsPolygon(b: BBox) {
  return { type: 'Feature' as const, properties: { kind: 'analysis' }, geometry: { type: 'Polygon' as const, coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] } }
}

function ensureGeoJson(map: MlMap, id: string, data: GeoJSON.GeoJSON) {
  const src = map.getSource(id) as GeoJSONSource | undefined
  if (src) src.setData(data)
  else map.addSource(id, { type: 'geojson', data, promoteId: 'id' })
}

export interface SyncContext {
  role: MapRole
  analysisId: string | null
  completed: boolean
  bounds: BBox | null
  hasNdvi: boolean
  falseColor: boolean
  layerState: Record<string, LayerState>
  catalog: LayerInfo[]
  fc: FeatureCollectionLite | null
  regions: Region[]
  selectedId: string | null
  hoveredId: string | null
  envTileUrl: (l: LayerInfo) => string | null
}

const vis = (ctx: SyncContext, id: string, forced?: boolean) => forced ?? ctx.layerState[id]?.visible ?? false
const opa = (ctx: SyncContext, id: string, d = 1) => ctx.layerState[id]?.opacity ?? d

/** Idempotently reconcile every overlay on `map` with the shared application state. */
export function syncLayers(map: MlMap, ctx: SyncContext): void {
  if (!map.isStyleLoaded() && !map.getStyle()) return
  const { analysisId, completed } = ctx

  // ---- analysis rasters ---------------------------------------------------------------------------------------
  const wantBefore = ctx.role === 'before' ? true : ctx.role === 'after' ? false : vis(ctx, 'imagery-before')
  const wantAfter = ctx.role === 'after' ? true : ctx.role === 'before' ? false : vis(ctx, 'imagery-after')
  const raster = (id: string, layer: 'before' | 'after' | 'score' | 'delta_ndvi', want: boolean, opacity: number, falseColor = false) => {
    if (analysisId && completed) ensureRaster(map, id, analysisTileUrl(analysisId, layer, { falseColor }), opacity, want)
    else removeRaster(map, id)
  }
  raster('imagery-before', 'before', wantBefore, ctx.role === 'single' ? opa(ctx, 'imagery-before') : 1, ctx.falseColor)
  raster('imagery-after', 'after', wantAfter, ctx.role === 'single' ? opa(ctx, 'imagery-after') : 1, ctx.falseColor)
  raster('change-score', 'score', ctx.role !== 'before' && vis(ctx, 'change-score'), opa(ctx, 'change-score', 0.7))
  if (ctx.hasNdvi) raster('delta-ndvi', 'delta_ndvi', ctx.role !== 'before' && vis(ctx, 'delta-ndvi'), opa(ctx, 'delta-ndvi', 0.8))
  else removeRaster(map, 'delta-ndvi')

  // ---- environmental / risk layers ----------------------------------------------------------------------------
  const live = new Set<string>()
  for (const l of ctx.catalog) {
    if (l.group === 'change') continue
    const st = ctx.layerState[l.id]
    const url = ctx.envTileUrl(l)
    const id = `env-${l.id}`
    if (st?.visible && url) {
      ensureRaster(map, id, url, st.opacity, true, l.max_zoom ?? 9)
      live.add(id)
    } else removeRaster(map, id)
  }
  for (const s of Object.keys(map.getStyle()?.sources ?? {})) if (s.startsWith('env-') && !live.has(s)) removeRaster(map, s)

  // ---- AOI + monitored regions --------------------------------------------------------------------------------
  const showAoi = vis(ctx, 'aoi')
  const aoiFc: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: ctx.bounds && analysisId ? [boundsPolygon(ctx.bounds) as GeoJSON.Feature] : [] }
  ensureGeoJson(map, 'aoi', aoiFc)
  if (!map.getLayer('aoi-fill')) map.addLayer({ id: 'aoi-fill', type: 'fill', source: 'aoi', paint: { 'fill-color': '#6EE7A0', 'fill-opacity': 0.03 } }, beforeIdFor(map, 'aoi-fill'))
  if (!map.getLayer('aoi-line')) map.addLayer({ id: 'aoi-line', type: 'line', source: 'aoi', paint: { 'line-color': '#6EE7A0', 'line-width': 1.4, 'line-dasharray': [3, 2], 'line-opacity': 0.9 } }, beforeIdFor(map, 'aoi-line'))
  const regionFc: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: ctx.regions.filter((r) => r.geometry).map((r) => ({ type: 'Feature', id: r.id, properties: { id: r.id, name: r.name, risk: r.risk_level }, geometry: r.geometry as GeoJSON.Geometry })),
  }
  ensureGeoJson(map, 'regions', regionFc)
  if (!map.getLayer('regions-fill')) map.addLayer({ id: 'regions-fill', type: 'fill', source: 'regions', paint: { 'fill-color': '#818CF8', 'fill-opacity': 0.05 } }, beforeIdFor(map, 'regions-fill'))
  if (!map.getLayer('regions-line')) map.addLayer({ id: 'regions-line', type: 'line', source: 'regions', paint: { 'line-color': '#818CF8', 'line-width': 1.2, 'line-opacity': 0.8 } }, beforeIdFor(map, 'regions-line'))
  for (const id of ['aoi-fill', 'aoi-line', 'regions-fill', 'regions-line']) map.setLayoutProperty(id, 'visibility', showAoi ? 'visible' : 'none')

  // ---- change polygons ----------------------------------------------------------------------------------------
  const showFeatures = ctx.role !== 'before' && vis(ctx, 'change-polygons')
  const op = opa(ctx, 'change-polygons', 0.85)
  const data: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: (ctx.fc?.features ?? []) as unknown as GeoJSON.Feature[] }
  ensureGeoJson(map, 'features', data)
  if (!map.getLayer('features-fill')) {
    map.addLayer({ id: 'features-fill', type: 'fill', source: 'features', paint: {
      'fill-color': SEVERITY_MATCH as never, 'fill-opacity': ['case', ['==', ['get', 'review_status'], 'rejected'], 0.06, 0.26] as never } }, beforeIdFor(map, 'features-fill'))
    map.addLayer({ id: 'features-line', type: 'line', source: 'features', paint: {
      'line-color': SEVERITY_MATCH as never, 'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.8, 16, 2.4] as never } }, beforeIdFor(map, 'features-line'))
    map.addLayer({ id: 'features-hover', type: 'fill', source: 'features', filter: ['==', ['get', 'id'], ''], paint: { 'fill-color': '#FFFFFF', 'fill-opacity': 0.22 } }, beforeIdFor(map, 'features-hover'))
    map.addLayer({ id: 'features-selected', type: 'line', source: 'features', filter: ['==', ['get', 'id'], ''], paint: { 'line-color': '#FFFFFF', 'line-width': 3.2, 'line-blur': 0.4 } }, beforeIdFor(map, 'features-selected'))
  }
  for (const id of ['features-fill', 'features-line']) map.setLayoutProperty(id, 'visibility', showFeatures ? 'visible' : 'none')
  map.setPaintProperty('features-line', 'line-opacity', op)
  map.setFilter('features-hover', ['==', ['get', 'id'], showFeatures ? ctx.hoveredId ?? '' : ''])
  map.setFilter('features-selected', ['==', ['get', 'id'], showFeatures ? ctx.selectedId ?? '' : ''])
  map.setLayoutProperty('features-hover', 'visibility', showFeatures ? 'visible' : 'none')
  map.setLayoutProperty('features-selected', 'visibility', showFeatures ? 'visible' : 'none')
}
