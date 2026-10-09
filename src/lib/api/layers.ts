/** Layer catalogue types (mirrors backend `app/layers`). Filled in with the layer framework. */
export type LayerGroup = 'environmental' | 'risk' | 'change'
export interface LayerInfo {
  id: string; name: string; group: LayerGroup; provider: string; data_type: string; render_type: string; crs: string
  tile_url?: string | null; attribution: string; limitations: string[]
  legend: { kind: 'gradient' | 'categorical'; unit?: string; stops?: { value: string; color: string }[]; min?: number; max?: number } | null
  temporal: { kind: 'static' | 'daily' | 'monthly' | 'analysis'; default_time?: string | null; min?: string | null; max?: string | null } | null
  default_visible: boolean; default_opacity: number
  availability: 'available' | 'unavailable' | 'needs_credentials' | 'unknown' | 'requires_analysis'
  availability_detail: string | null; last_checked_at: string | null; last_updated_at: string | null
  max_zoom?: number | null
}
