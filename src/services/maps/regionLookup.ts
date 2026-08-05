/**
 * Region lookup utilities for map interaction.
 *
 * Shared between MapLibre (GeoJSON layers) and InteractiveMap (SVG polygons).
 * Both implementations ultimately call setSelectedRegion() via Zustand —
 * this module provides the geographic data they need.
 */

import { REGIONS } from '@/lib/mockData'

// ─── GeoJSON Conversion ──────────────────────────────────────────────────────

/**
 * Convert all region bounding boxes into a GeoJSON FeatureCollection
 * suitable for adding as a MapLibre source.
 *
 * Each feature carries `properties.regionId` matching `Region.id`.
 */
export function regionsToGeoJSON() {
  return {
    type: 'FeatureCollection' as const,
    features: REGIONS.map((region) => ({
      type: 'Feature' as const,
      properties: {
        regionId: region.id,
        name: region.name,
      },
      geometry: {
        type: 'Polygon' as const,
        coordinates: [[
          [region.bbox.minLon, region.bbox.minLat],
          [region.bbox.maxLon, region.bbox.minLat],
          [region.bbox.maxLon, region.bbox.maxLat],
          [region.bbox.minLon, region.bbox.maxLat],
          [region.bbox.minLon, region.bbox.minLat], // close the ring
        ]],
      },
    })),
  }
}

// ─── Coordinate Lookup ────────────────────────────────────────────────────────

/**
 * Find which region a geographic coordinate falls within.
 * Returns the region ID or null if the point is outside all regions.
 *
 * Useful as a fallback when MapLibre layer queries don't return results.
 */
export function findRegionByCoordinates(lon: number, lat: number): string | null {
  for (const region of REGIONS) {
    const { minLon, minLat, maxLon, maxLat } = region.bbox
    if (lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat) {
      return region.id
    }
  }
  return null
}
