/** Sentinel search / acquisition types (mirrors backend `app/schemas/sentinel.py`). */
import type { Position } from './types'
export interface DateWindow { start: string; end: string }
export interface SentinelSearchBody {
  project_id?: string; aoi_id?: string; bbox?: [number, number, number, number]; center?: Position; radius_m?: number
  geometry?: unknown; before: DateWindow; after: DateWindow; max_cloud_cover_pct?: number; limit?: number
}
export interface Scene {
  product_id: string; collection: string; provider: string; acquired_at: string; cloud_cover_pct: number | null
  footprint: unknown | null; coverage_of_aoi_pct: number | null; thumbnail_url: string | null; resolution_m: number | null
  platform: string | null; processing_level: string | null; properties: Record<string, unknown>
}
export interface SentinelSearchResult {
  provider: string; aoi_geometry: unknown; aoi_area_km2: number; before: Scene[]; after: Scene[]
  suggested_before: string | null; suggested_after: string | null; suggestion_rule: string; warnings: string[]
}
export interface AcquireBody {
  project_id: string; aoi_id?: string; aoi_geometry?: unknown; before_product_id?: string; after_product_id?: string
  before?: DateWindow; after?: DateWindow; max_cloud_cover_pct?: number; auto_select?: boolean; pixel_size_m?: number
  name?: string; start_analysis?: boolean; config?: Record<string, unknown>
}
export interface AcquireResult { analysis_id: string; status: string; before_product_id: string | null; after_product_id: string | null; message: string }

export interface MlChangeStats {
  analyzed_area_m2: number; changed_fraction: number; largest_m2: number; median_m2: number
  size_classes: { label: string; count: number; area_m2: number }[]
}
export interface MlChangeMeta {
  stats: MlChangeStats
  model_id: string | null; model_name: string | null; input_pixel_size_m: number; model_fed_at_m: number; masked_cloud_pct: number
  feature_count: number; returned: number; total_changed_area_m2: number; warnings: string[]; notes: string[]; disclaimer: string
  timings_s: Record<string, number>
}
export interface MlChangeCollection {
  type: 'FeatureCollection'; metadata: MlChangeMeta
  features: { type: 'Feature'; id: number; geometry: { type: string; coordinates: unknown }; properties: { id: number; point: [number, number]; area_m2: number; score: number | null; magnitude: number; severity: string } }[]
}

/** ML result for non-georeferenced images: geometry is in IMAGE PIXEL coordinates (x right, y down). */
export interface PlainChangeCollection {
  type: 'FeatureCollection'
  metadata: Omit<MlChangeMeta, 'model_fed_at_m' | 'total_changed_area_m2'> & {
    model_fed_at_m: number | null; total_changed_area_m2: number | null; image_size: [number, number]; pixel_size_known: boolean
    pixel_size_m: number | null; model_choice_reason: string; total_changed_px: number; source: string
  }
  features: { type: 'Feature'; id: number; geometry: { type: string; coordinates: number[][][] }; properties: { id: number; area_px: number; area_m2: number | null; point: [number, number]; magnitude: number } }[]
}
