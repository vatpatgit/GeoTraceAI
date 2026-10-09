import type { Analysis } from '@/lib/api'
import { analysisTileUrl } from '@/lib/api/client'
import type { LayerInfo } from '@/lib/api/layers'

export type RenderTarget = 'maplibre' | 'cesium'

const hasNdvi = (a: Analysis | null | undefined): boolean =>
  !!a && a.status === 'completed' && !!a.processing?.grid?.roles?.includes('red') && !!a.processing?.grid?.roles?.includes('nir')

/** Availability as the user should see it now (analysis-derived layers depend on the active analysis). */
export function effectiveAvailability(l: LayerInfo, analysis: Analysis | null | undefined): LayerInfo['availability'] {
  if (l.render_type === 'analysis_raster') return hasNdvi(analysis) ? 'available' : 'requires_analysis'
  return l.availability
}

/** Concrete tile URL template for a layer, or null if it cannot be drawn right now. */
export function layerTileUrl(l: LayerInfo, analysis: Analysis | null | undefined, target: RenderTarget = 'maplibre'): string | null {
  if (l.render_type === 'analysis_raster') {
    if (!hasNdvi(analysis) || !analysis) return null
    return analysisTileUrl(analysis.id, l.id === 'ndvi-before' ? 'ndvi_before' : 'ndvi_after')
  }
  if (!l.tile_url) return null
  if (l.availability === 'unavailable' || l.availability === 'needs_credentials') return null
  let url = l.tile_url.replace('{time}', l.temporal?.default_time ?? 'default')
  if (target === 'cesium') url = url.replace('{bbox-epsg-3857}', '{westProjected},{southProjected},{eastProjected},{northProjected}')
  return url
}

/** True for layers whose tiles come from GeoTrace itself (and therefore need the bearer token). */
export const isAnalysisLayer = (l: LayerInfo): boolean => l.render_type === 'analysis_raster'
