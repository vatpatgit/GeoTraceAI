import { CARTO_DARK_MATTER, ESRI_WORLD_IMAGERY } from '@/services/maps/tileSources'

export const SATELLITE_LAYER = 'basemap-satellite'
export const DARK_LAYER = 'basemap-dark'

/** Style containing both basemaps; the active one is toggled by visibility (no style swap => overlays survive). */
export function baseStyle(initial: 'satellite' | 'dark') {
  return {
    version: 8 as const,
    sources: {
      satellite: { type: 'raster' as const, tiles: ESRI_WORLD_IMAGERY.tiles, tileSize: ESRI_WORLD_IMAGERY.tileSize, maxzoom: ESRI_WORLD_IMAGERY.maxzoom, attribution: ESRI_WORLD_IMAGERY.attribution },
      dark: { type: 'raster' as const, tiles: CARTO_DARK_MATTER.tiles, tileSize: CARTO_DARK_MATTER.tileSize, maxzoom: CARTO_DARK_MATTER.maxzoom, attribution: CARTO_DARK_MATTER.attribution },
    },
    layers: [
      { id: 'bg', type: 'background' as const, paint: { 'background-color': '#04070c' } },
      { id: DARK_LAYER, type: 'raster' as const, source: 'dark', layout: { visibility: initial === 'dark' ? ('visible' as const) : ('none' as const) } },
      { id: SATELLITE_LAYER, type: 'raster' as const, source: 'satellite', layout: { visibility: initial === 'satellite' ? ('visible' as const) : ('none' as const) } },
    ],
  }
}
