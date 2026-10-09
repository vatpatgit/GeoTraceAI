/** Live hazard alerts (earthquake / fire hotspot / storm) matched to the user's AOIs; mirrors backend `app/api/hazards.py`.
 *  These are third-party observations matched by distance. They are NOT satellite change detections from GeoTrace analyses. */
export type HazardKind = 'earthquake' | 'fire' | 'storm'
export type HazardSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface HazardAlert {
  id: string; aoi_id: string; aoi_name: string | null; kind: HazardKind; title: string; severity: HazardSeverity
  lat: number; lon: number; distance_km: number; occurred_at: string | null; details: Record<string, unknown>
  status: 'active' | 'expired'; first_seen_at: string; last_seen_at: string; read_at: string | null
}
export interface HazardRefresh {
  aois: number; new: number; updated: number; expired: number; active: number; cached: boolean
  fetched: Record<string, number>; errors: Record<string, string>; checked_at: string
}
export interface HazardStatus {
  enabled: boolean; provider: string; scheduled_refresh_minutes: number; max_age_hours: number
  kinds: Record<string, { radius_km: number; min_magnitude?: number; note?: string }>
  not_supported: Record<string, string>
}

export const HAZARD_LABEL: Record<HazardKind, string> = { earthquake: 'Earthquake', fire: 'Fire hotspots', storm: 'Storm / weather event' }
export const HAZARD_RANK: Record<HazardSeverity, number> = { low: 0, medium: 1, high: 2, critical: 3 }
