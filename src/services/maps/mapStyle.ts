/**
 * MapLibre style builder.
 *
 * Constructs a complete MapLibre Style Specification object from a TileSourceConfig.
 * BaseMap calls createSatelliteStyle() and passes the result to `new Map({ style })`.
 */

import type { TileSourceConfig } from './tileSources'
import { DEFAULT_TILE_SOURCE } from './tileSources'

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
  }>
}

// ─── Builder ──────────────────────────────────────────────────────────────────

export function createSatelliteStyle(
  source: TileSourceConfig = DEFAULT_TILE_SOURCE,
): MapStyle {
  return {
    version: 8,
    sources: {
      [source.id]: {
        type: source.type,
        tiles: source.tiles,
        tileSize: source.tileSize,
        maxzoom: source.maxzoom,
        attribution: source.attribution,
      },
    },
    layers: [
      {
        id: `${source.id}-layer`,
        type: 'raster',
        source: source.id,
      },
    ],
  }
}
