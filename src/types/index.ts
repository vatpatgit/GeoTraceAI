/**
 * TypeScript interfaces for TerraTrack mock API responses
 * TODO: Replace with actual API response types when backend is integrated
 */

export interface BoundingBox {
  minLon: number
  minLat: number
  maxLon: number
  maxLat: number
}

export interface DateRange {
  start: string // ISO date string
  end: string
}

export interface Region {
  id: string
  name: string
  bbox: BoundingBox
  defaultDateRange: DateRange
  areaKm2: number
  description?: string | null
  riskLevel?: string
  geometry?: {
    type: string
    coordinates: number[][][] | number[][][][]
  } | null
}

export interface TimeSeriesDataPoint {
  date: string // ISO date string
  change_area_km2: number
  avg_confidence: number
  alert_count: number
}

export interface ChangePolygon {
  type: 'Feature'
  geometry: {
    type: 'Polygon'
    coordinates: number[][][]
  }
  properties: {
    confidence: number
    change_type: string
  }
}

export interface ChangeFeatureCollection {
  type: 'FeatureCollection'
  features: ChangePolygon[]
}

export interface ConfidencePoint {
  lon: number
  lat: number
  confidence: number
}

export interface ConfidenceData {
  grid: ConfidencePoint[]
}

export type UserRole = 'Admin' | 'Researcher' | 'Viewer'

export type ViewMode = 'globe' | 'satellite' | 'map'

export interface MapViewState {
  viewMode: ViewMode
  center: [number, number] // [lon, lat]
  zoom: number
  bearing?: number
  pitch?: number
  selectedRegion: string | null
  currentDate: string
  dateRange: DateRange
  activeLayers: {
    satellite: boolean
    changeMask: boolean
    confidence: boolean
  }
  comparisonMode: boolean
  comparisonDate: string | null
}

export interface AlertConfig {
  sensitivity: number // 0-100
  email: string
  webhookUrl: string
}

