/**
 * Region GeoJSON loader.
 *
 * Imports the static GeoJSON file and provides typed access.
 * Adding a new monitoring region requires only editing regions.geojson —
 * no code changes in this file or any component.
 */

import regionsData from '@/data/geojson/regions.geojson'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface RegionMetadata {
  continent: string
  riskLevel: 'low' | 'moderate' | 'high' | 'critical'
  defaultZoom: number
}

export interface RegionFeatureProperties {
  id: string
  name: string
  metadata: RegionMetadata
}

export interface RegionFeature {
  type: 'Feature'
  id: string
  properties: RegionFeatureProperties
  geometry: {
    type: 'Polygon' | 'MultiPolygon'
    coordinates: number[][][] | number[][][][]
  }
}

export interface RegionFeatureCollection {
  type: 'FeatureCollection'
  features: RegionFeature[]
}

// ─── Loader ───────────────────────────────────────────────────────────────────

/**
 * Returns the full region GeoJSON FeatureCollection.
 * The data is statically imported and bundled — no network request.
 */
export function loadRegionGeoJSON(): RegionFeatureCollection {
  return regionsData as RegionFeatureCollection
}

/**
 * Look up a single region feature by ID.
 */
export function getRegionFeature(regionId: string): RegionFeature | undefined {
  const data = loadRegionGeoJSON()
  return data.features.find((f) => f.properties.id === regionId)
}
