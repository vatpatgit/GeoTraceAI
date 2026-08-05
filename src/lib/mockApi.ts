/**
 * Mock API client for TerraTrack
 * TODO: Replace all fetch calls with actual API endpoints when backend is ready
 * Example: fetch('/api/v1/regions') -> fetch('/mocks/regions.json')
 */

import type { Region, TimeSeriesDataPoint, ChangeFeatureCollection, ConfidenceData } from '@/types'

const API_BASE = '/mocks'

export async function fetchRegions(): Promise<Region[]> {
  // TODO: Replace with fetch('/api/v1/regions')
  const response = await fetch(`${API_BASE}/regions.json`)
  if (!response.ok) {
    throw new Error('Failed to fetch regions')
  }
  return response.json()
}

export async function fetchTimeSeries(regionId: string): Promise<TimeSeriesDataPoint[]> {
  // TODO: Replace with fetch(`/api/v1/timeseries?region=${regionId}`)
  const response = await fetch(`${API_BASE}/timeseries.json`)
  if (!response.ok) {
    throw new Error('Failed to fetch time series')
  }
  const data = await response.json()
  return data[regionId] || []
}

export async function fetchChanges(
  regionId: string,
  date: string
): Promise<ChangeFeatureCollection | null> {
  // TODO: Replace with fetch(`/api/v1/changes?region=${regionId}&date=${date}`)
  const response = await fetch(`${API_BASE}/changes.json`)
  if (!response.ok) {
    return null
  }
  const data = await response.json()
  return data[regionId]?.[date] || null
}

export async function fetchConfidence(regionId: string): Promise<ConfidenceData | null> {
  // TODO: Replace with fetch(`/api/v1/confidence?region=${regionId}`)
  const response = await fetch(`${API_BASE}/confidence.json`)
  if (!response.ok) {
    return null
  }
  const data = await response.json()
  return data[regionId] || null
}

/**
 * Get confidence value for a specific point (mock implementation)
 * In production, this would query a spatial database or tile service
 */
export function getConfidenceAtPoint(
  lon: number,
  lat: number,
  regionId: string
): Promise<number> {
  // TODO: Replace with spatial query to backend
  return fetchConfidence(regionId).then((data) => {
    if (!data) return 0.85 // Default confidence
    // Simple nearest neighbor lookup (mock)
    const distances = data.grid.map((point) => ({
      point,
      distance: Math.sqrt(
        Math.pow(point.lon - lon, 2) + Math.pow(point.lat - lat, 2)
      ),
    }))
    distances.sort((a, b) => a.distance - b.distance)
    return distances[0]?.point.confidence || 0.85
  })
}

/**
 * Get overlay image URL for a region and date
 * TODO: Replace with actual tile service URL pattern
 * Example: `/tiles/${regionId}/${date}/{z}/{x}/{y}.png`
 */
export function getOverlayUrl(regionId: string, date: string, layer: string): string {
  // For now, return a placeholder
  // TODO: Replace with actual tile URL: `/tiles/${regionId}/${date}/${layer}/{z}/{x}/{y}.png`
  return `/mocks/overlays/${regionId}/${date}-${layer}.png`
}

