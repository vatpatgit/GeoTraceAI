/**
 * MapLibre style builder.
 *
 * Constructs a complete MapLibre Style Specification object from a TileSourceConfig.
 * BaseMap calls createSatelliteStyle() and passes the result to `new Map({ style })`.
 */

import type { TileSourceConfig } from './tileSources'
import { ESRI_WORLD_IMAGERY, CARTO_DARK_MATTER, DEFAULT_TILE_SOURCE } from './tileSources'

// ─── Style Spec Interface (provider-agnostic) ─────────────────────────────────
// Defined locally so the service layer has zero runtime dependency on maplibre-gl.

export interface MapStyle {
  version: 8
  sources: Record<string, {
    type: string
    tiles: string[]
    tileSize: number
    maxzoom?: number
    attribution?: string
  }>
  layers: Array<{
    id: string
    type: string
    source: string
    layout?: Record<string, any>
    paint?: Record<string, any>
  }>
  sky?: Record<string, any>
}

// ─── Builder ──────────────────────────────────────────────────────────────────

export const MAP_LAYERS = {
  SATELLITE: 'satellite-base-layer',
  MAP: 'carto-dark-layer',
} as const

export function createUnifiedMapStyle(
  satelliteSource: TileSourceConfig = ESRI_WORLD_IMAGERY,
  mapSource: TileSourceConfig = CARTO_DARK_MATTER,
): MapStyle {
  return {
    version: 8,
    sources: {
      [satelliteSource.id]: {
        type: satelliteSource.type,
        tiles: satelliteSource.tiles,
        tileSize: satelliteSource.tileSize,
        maxzoom: satelliteSource.maxzoom,
        attribution: satelliteSource.attribution,
      },
      [mapSource.id]: {
        type: mapSource.type,
        tiles: mapSource.tiles,
        tileSize: mapSource.tileSize,
        maxzoom: mapSource.maxzoom,
        attribution: mapSource.attribution,
      },
    },
    layers: [
      {
        id: MAP_LAYERS.MAP,
        type: 'raster',
        source: mapSource.id,
        layout: {
          visibility: 'none',
        },
      },
      {
        id: MAP_LAYERS.SATELLITE,
        type: 'raster',
        source: satelliteSource.id,
        layout: {
          visibility: 'visible',
        },
      },
    ],
  }
}

export function createSatelliteStyle(
  source: TileSourceConfig = DEFAULT_TILE_SOURCE,
): MapStyle {
  return createUnifiedMapStyle(source)
}

