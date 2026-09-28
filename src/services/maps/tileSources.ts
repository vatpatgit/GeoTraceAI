/**
 * Tile source configurations.
 *
 * To switch satellite imagery providers, change the DEFAULT_TILE_SOURCE export.
 * The rest of the application (BaseMap, styles, attribution) adapts automatically.
 */

import { ESRI_WORLD_IMAGERY_ATTRIBUTION, CARTO_DARK_MATTER_ATTRIBUTION } from './attribution'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TileSourceConfig {
  /** Unique identifier used as the source key in the style spec */
  id: string
  /** Raster (satellite/aerial) or vector (street maps) */
  type: 'raster' | 'vector'
  /** XYZ tile URL template(s) — {z}/{y}/{x} will be substituted */
  tiles: string[]
  /** Tile size in pixels (256 is standard for most providers) */
  tileSize: number
  /** Maximum zoom level the provider supports */
  maxzoom: number
  /** Legal attribution HTML — rendered by the map control */
  attribution: string
}

// ─── Providers ────────────────────────────────────────────────────────────────

export const ESRI_WORLD_IMAGERY: TileSourceConfig = {
  id: 'satellite',
  type: 'raster',
  tiles: [
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  ],
  tileSize: 256,
  maxzoom: 19,
  attribution: ESRI_WORLD_IMAGERY_ATTRIBUTION,
}

export const CARTO_DARK_MATTER: TileSourceConfig = {
  id: 'carto-dark',
  type: 'raster',
  tiles: [
    'https://a.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png',
    'https://b.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png',
    'https://c.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png',
    'https://d.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png',
  ],
  tileSize: 256,
  maxzoom: 20,
  attribution: CARTO_DARK_MATTER_ATTRIBUTION,
}

// ─── Default ──────────────────────────────────────────────────────────────────
// Change this single line to swap the satellite provider globally.

export const DEFAULT_TILE_SOURCE: TileSourceConfig = ESRI_WORLD_IMAGERY

