/**
 * TerraTrack API client.
 *
 * Prefer the live backend when it is available and gracefully fall back to local mock data
 * for the demo experience when the backend is not running.
 */

import type { Region, TimeSeriesDataPoint, ChangeFeatureCollection, ConfidenceData, UserRole } from '@/types'

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const MOCK_BASE = '/mocks'

type BackendRegion = {
  id: string
  name: string
  description?: string | null
  center_lat: number
  center_lng: number
  area_km2: number
  risk_level: string
  geometry?: {
    type?: string
    coordinates?: number[][][]
  } | null
  metadata_json?: Record<string, unknown> | null
  created_at?: string
}

type BackendRegionsResponse = {
  regions: BackendRegion[]
  total: number
}

type BackendTrendResponse = {
  metric?: string
  region_id?: string
  data: Array<{ date: string; value: number }>
}

class ApiError extends Error {
  constructor(public status: number) {
    super(`Backend request failed: ${status}`)
  }
}

async function getAccessToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null

  const existing = window.localStorage.getItem('terratrack_access_token')
  if (existing) return existing

  return null
}

async function requestBackend<T>(path: string, fallback: () => Promise<T>): Promise<T> {
  try {
    const token = await getAccessToken()
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new ApiError(response.status)
      }
      throw new Error(`Backend request failed: ${response.status}`)
    }

    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    return fallback()
  }
}

export async function loginWithCredentials(email: string, password: string) {
  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }).toString(),
    })

    if (!response.ok) {
      window.localStorage.removeItem('terratrack_access_token')
      return null
    }

    const data = await response.json()
    const token = data.access_token as string | undefined
    if (!token) return null

    window.localStorage.setItem('terratrack_access_token', token)
    return { token, user: await fetchCurrentUser() }
  } catch {
    return null
  }
}

export async function fetchCurrentUser(): Promise<{ id: string; email: string; name: string; role: UserRole } | null> {
  if (typeof window === 'undefined') return null

  const token = localStorage.getItem('terratrack_access_token')
  if (!token) return null

  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })

    if (!response.ok) return null

    const data = await response.json()
    const role = (String(data.role || 'Viewer').charAt(0).toUpperCase() + String(data.role || 'Viewer').slice(1)) as UserRole
    return {
      id: data.id,
      email: data.email,
      name: data.name,
      role: role === 'Admin' || role === 'Researcher' || role === 'Viewer' ? role : 'Viewer',
    }
  } catch {
    return null
  }
}

export function logoutUser(): void {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('terratrack_access_token')
  }
}

function normalizeRegion(region: BackendRegion): Region {
  const coords = region.geometry?.coordinates?.[0] || []
  const lngs = coords.map((point) => point[0]).filter((value): value is number => typeof value === 'number')
  const lats = coords.map((point) => point[1]).filter((value): value is number => typeof value === 'number')

  return {
    id: region.id,
    name: region.name,
    bbox: {
      minLon: lngs.length ? Math.min(...lngs) : -70,
      minLat: lats.length ? Math.min(...lats) : -5,
      maxLon: lngs.length ? Math.max(...lngs) : -60,
      maxLat: lats.length ? Math.max(...lats) : 5,
    },
    defaultDateRange: {
      start: '2024-01-01',
      end: '2024-01-30',
    },
    areaKm2: Number(region.area_km2 || 0),
    description: region.description,
    riskLevel: region.risk_level,
    geometry: region.geometry ? {
      type: region.geometry.type || 'Polygon',
      coordinates: region.geometry.coordinates || [],
    } : null,
  }
}

export async function fetchRegions(): Promise<Region[]> {
  const fallback = async () => {
    const response = await fetch(`${MOCK_BASE}/regions.json`)
    if (!response.ok) throw new Error('Failed to fetch regions')
    return response.json()
  }

  const data = await requestBackend<BackendRegionsResponse | BackendRegion[]>('/regions/', fallback)
  if (Array.isArray(data)) return data.map(normalizeRegion)
  return (data.regions || []).map(normalizeRegion)
}

export async function fetchTimeSeries(regionId: string): Promise<TimeSeriesDataPoint[]> {
  const fallback = async () => {
    const response = await fetch(`${MOCK_BASE}/timeseries.json`)
    if (!response.ok) throw new Error('Failed to fetch time series')
    const data = await response.json()
    return data[regionId] || []
  }

  const data = await requestBackend<BackendTrendResponse>(
    `/analytics/trends?region_id=${encodeURIComponent(regionId)}&days=30&metric=changes`,
    fallback
  )

  return (data.data || []).map((point) => ({
    date: point.date,
    change_area_km2: point.value,
    avg_confidence: 0.8,
    alert_count: 0,
  }))
}

export async function fetchChanges(
  regionId: string,
  date: string
): Promise<ChangeFeatureCollection | null> {
  const fallback = async () => {
    const response = await fetch(`${MOCK_BASE}/changes.json`)
    if (!response.ok) return null
    const data = await response.json()
    return data[regionId]?.[date] || null
  }

  const data = await requestBackend<Array<Record<string, unknown>>>(
    `/changes?region_id=${encodeURIComponent(regionId)}&date_from=${encodeURIComponent(date)}&date_to=${encodeURIComponent(date)}&limit=25`,
    fallback
  )

  if (!Array.isArray(data) || data.length === 0) return null

  return {
    type: 'FeatureCollection',
    features: data
      .filter((item) => item.geometry)
      .map((item) => ({
        type: 'Feature' as const,
        geometry: item.geometry as ChangeFeatureCollection['features'][number]['geometry'],
        properties: {
          confidence: Number(item.confidence ?? 0.8),
          change_type: String(item.change_type ?? 'change'),
        },
      })),
  }
}

export async function fetchConfidence(regionId: string): Promise<ConfidenceData | null> {
  const fallback = async () => {
    const response = await fetch(`${MOCK_BASE}/confidence.json`)
    if (!response.ok) return null
    const data = await response.json()
    return data[regionId] || null
  }

  try {
    const analytics = await requestBackend<Record<string, unknown>>(
      `/analytics/region/${encodeURIComponent(regionId)}`,
      fallback
    )
    const confidence = analytics.avg_confidence as number | undefined
    if (typeof confidence !== 'number') return null

    return {
      grid: [
        { lon: 0, lat: 0, confidence },
        { lon: 0.01, lat: 0.01, confidence },
      ],
    }
  } catch {
    return fallback()
  }
}

export function getConfidenceAtPoint(
  lon: number,
  lat: number,
  regionId: string
): Promise<number> {
  return fetchConfidence(regionId).then((data) => {
    if (!data) return 0.85
    const distances = data.grid.map((point) => ({
      point,
      distance: Math.sqrt(Math.pow(point.lon - lon, 2) + Math.pow(point.lat - lat, 2)),
    }))
    distances.sort((a, b) => a.distance - b.distance)
    return distances[0]?.point.confidence || 0.85
  })
}

export function getOverlayUrl(regionId: string, date: string, layer: string): string {
  return `/mocks/overlays/${regionId}/${date}-${layer}.png`
}
