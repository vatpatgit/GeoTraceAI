/** Weather alerts (OpenWeather Alerts API via the GeoTrace backend; mirrors backend `app/schemas/weather.py`). */
import type { GeoJSONGeometry } from './types'

export type WeatherSeverity = 'unknown' | 'minor' | 'moderate' | 'severe' | 'extreme'
export const WEATHER_SEVERITIES: WeatherSeverity[] = ['unknown', 'minor', 'moderate', 'severe', 'extreme']

export interface WeatherAlert {
  id: string; aoi_id: string; aoi_name: string | null; provider: string; source_alert_id: string; source: string | null
  title: string; description: string | null; tags: string[]; severity: WeatherSeverity; urgency: string; certainty: string
  industry: Record<string, unknown>[]
  /** Provider-supplied alert area. NOT a satellite-derived change polygon and not the extent of physical damage. */
  geometry: GeoJSONGeometry | null
  start_time: string | null; end_time: string | null; status: 'active' | 'expired'; change_count: number
  first_seen_at: string; last_seen_at: string; last_checked_at: string; notified_at: string | null
}
export interface AoiWeatherState {
  aoi_id: string; aoi_name: string; last_checked_at: string | null; last_status: 'ok' | 'error' | null; last_error: string | null
  alert_count: number; monitoring: boolean
}
export interface WeatherAlertList { configured: boolean; items: WeatherAlert[]; aois: AoiWeatherState[] }
export interface WeatherRefresh {
  aoi_id: string; checked_at: string; cached: boolean; new: number; updated: number; unchanged: number; expired: number; total_active: number
  items: WeatherAlert[]
}
export interface WeatherEvent { id: string; alert_id: string; aoi_id: string; kind: 'new' | 'updated'; changes: string[]; title: string; severity: WeatherSeverity; created_at: string; read_at: string | null }
export interface WeatherStatus { configured: boolean; scheduled_refresh_minutes: number; lookahead_hours: number; max_aoi_km2: number; sources: string[]; tags: string[] }
