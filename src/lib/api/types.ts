/**
 * API contract types. These mirror the FastAPI/Pydantic schemas in `backend/app/schemas` 1:1.
 * Conventions: snake_case keys; UUID strings; ISO-8601 UTC datetimes ("...Z"); GeoJSON in EPSG:4326 [lon, lat];
 * areas in square metres.
 */

export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type ReviewStatus = 'unreviewed' | 'confirmed' | 'rejected'
export type AnalysisStatus =
  | 'queued' | 'validating' | 'acquiring_imagery' | 'preprocessing' | 'detecting_changes'
  | 'polygonizing' | 'evaluating_alerts' | 'exporting' | 'completed' | 'failed' | 'cancelled'
export type InputType = 'upload' | 'sentinel' | 'demo'
export type DetectionMethod = 'auto' | 'spectral_cva' | 'ndvi_diff' | 'learned_siamese'
export type IncidentStatus = 'open' | 'acknowledged' | 'resolved'
export type DataOrigin = 'live' | 'demo'

export const TERMINAL_STATUSES: AnalysisStatus[] = ['completed', 'failed', 'cancelled']
export const SEVERITIES: Severity[] = ['low', 'medium', 'high', 'critical']

export type Position = [number, number]
export interface GeoJSONGeometry { type: 'Polygon' | 'MultiPolygon' | 'Point'; coordinates: unknown }
export type BBox = [number, number, number, number] // [min_lon, min_lat, max_lon, max_lat]

export interface Issue { level: 'error' | 'warning' | 'info'; code: string; message: string; details: Record<string, unknown> }

// ---------------------------------------------------------------------------------------------- auth / users
export interface UserMe { id: string; email: string; name: string; role: string; is_active: boolean; created_at: string }

// ---------------------------------------------------------------------------------------------- projects / aoi
export interface Project {
  id: string; name: string; description: string | null; owner_id: string; visibility: 'private' | 'shared'
  is_demo: boolean; created_at: string; updated_at: string; analysis_count: number; can_write: boolean
}
export interface Aoi {
  id: string; project_id: string; name: string; geometry: GeoJSONGeometry; bbox: BBox; area_km2: number
  source: string; region_id: string | null; created_at: string
}
export interface AoiCreate {
  name: string
  source?: 'polygon' | 'bbox' | 'point_radius' | 'region'
  geometry?: GeoJSONGeometry
  bbox?: BBox
  center?: Position
  radius_m?: number
  region_id?: string
}

// ---------------------------------------------------------------------------------------------- imagery
export interface ImageryAsset {
  id: string; project_id: string | null; kind: 'upload' | 'sentinel' | 'synthetic'; original_filename: string | null
  size_bytes: number; width: number; height: number; band_count: number; dtype: string; crs_epsg: number | null
  pixel_size_m: number; nodata: number | null; footprint: GeoJSONGeometry; bounds: BBox
  band_descriptions: (string | null)[] | null; band_map: Record<string, number> | null; band_map_confirmed: boolean
  band_notes: string[]; acquisition_start: string | null; acquisition_end: string | null; cloud_cover_pct: number | null
  source_provider: string | null; source_product_id: string | null; sha256: string; is_demo: boolean
  warnings: Issue[]; created_at: string
}
export interface PairValidation {
  ok: boolean; issues: Issue[]; analysis_crs_epsg: number | null; overlap: Record<string, unknown>
  resolution: Record<string, unknown>; bands: { common_roles: string[]; needs_confirmation: boolean; notes: string[] } & Record<string, unknown>
  suggested_pixel_size_m: number | null; model_available: boolean; suggested_method: string; suggested_method_reason: string
}

// ---------------------------------------------------------------------------------------------- analyses
export interface AnalysisSummary {
  feature_count: number; total_changed_area_m2: number; analyzed_area_m2: number; changed_fraction: number
  by_category: Record<string, number>; by_severity: Record<string, number>
  area_by_category_m2: Record<string, number>; area_by_severity_m2: Record<string, number>
  mean_magnitude: number | null; valid_fraction: number; method: string; pixel_size_m: number
  grid: { width: number; height: number; crs_epsg: number | null }
  alerts?: { rules_evaluated: number; incidents_created: number; suppressed_duplicates: number }
}
export interface Analysis {
  id: string; project_id: string; aoi_id: string | null; created_by: string; name: string; input_type: InputType
  status: AnalysisStatus; stage_message: string | null; progress: number
  error: { code: string; message: string; details?: Record<string, unknown> } | null
  cancel_requested: boolean; before_asset_id: string | null; after_asset_id: string | null
  before_date: string | null; after_date: string | null; method: string | null; method_reason: string | null
  model_id: string | null; config: Record<string, unknown>; summary: AnalysisSummary | null
  warnings: Issue[] | null; validation: Record<string, unknown> | null
  processing: {
    detection?: { method: string; magnitude_kind: string; confidence_kind: string | null; category_basis: string; notes: string[]; details: Record<string, unknown> }
    postprocess?: Record<string, unknown>; grid?: { width: number; height: number; pixel_size_m: number; crs_epsg: number | null; roles: string[]; valid_fraction: number }
    registration?: { reliable: boolean; magnitude_px: number; dx_px: number; dy_px: number }
    timings?: Record<string, number>
  } | null
  artifacts: string[]; bounds: BBox | null; is_demo: boolean; data_origin: DataOrigin
  created_at: string; started_at: string | null; finished_at: string | null
}
export interface AnalysisEvent { at: string; status: AnalysisStatus; progress: number; message: string | null }
export interface AnalysisCreate {
  project_id: string; name?: string; before_asset_id: string; after_asset_id: string
  before_date?: string | null; after_date?: string | null; aoi_id?: string | null
  config?: Record<string, unknown>; input_type?: InputType; acquisition_params?: Record<string, unknown>
}

export interface ChangeFeature {
  id: string; analysis_id: string; seq: number; category: string; category_basis: string
  area_m2: number; perimeter_m: number; centroid: Position; point_on_surface: Position
  magnitude: number; confidence: number | null; confidence_kind: string | null; delta_ndvi: number | null
  severity: Severity; severity_reasons: string[]; distance_to_boundary_m: number | null
  review_status: ReviewStatus; review_note: string | null; before_date: string | null; after_date: string | null
  bbox: BBox; geometry: GeoJSONGeometry
}
export interface FeaturePage { total: number; limit: number; offset: number; items: ChangeFeature[] }
export interface FeatureCollectionLite {
  type: 'FeatureCollection'; total: number; returned: number; truncated: boolean; is_demo: boolean
  features: { type: 'Feature'; id: string; geometry: GeoJSONGeometry; properties: { id: string; seq: number; category: string; severity: Severity; area_m2: number; confidence: number | null; magnitude: number; review_status: ReviewStatus; centroid: Position } }[]
}

export interface FeatureFilters {
  severity?: Severity[]; category?: string[]; review_status?: ReviewStatus[]
  min_area_m2?: number; max_area_m2?: number; min_confidence?: number; min_magnitude?: number
  bbox?: BBox; ids?: string[]; sort?: 'area_desc' | 'area_asc' | 'severity_desc' | 'confidence_desc' | 'seq'
}
export type ExportFormat = 'geojson' | 'gpkg' | 'csv'

// ---------------------------------------------------------------------------------------------- alerts
export interface AlertRule {
  id: string; owner_id: string; name: string; enabled: boolean; project_id: string | null; region_id: string | null
  aoi_id: string | null; region_relation: 'intersects' | 'within_distance'; distance_m: number | null
  categories: string[] | null; min_area_m2: number; min_severity: Severity; min_magnitude: number | null
  min_confidence: number | null; dedup_mode: 'none' | 'spatial'; dedup_window_days: number; dedup_overlap: number
  created_at: string; updated_at: string; last_evaluated_at: string | null; incident_count: number
}
export type AlertRuleInput = Partial<Omit<AlertRule, 'id' | 'owner_id' | 'created_at' | 'updated_at' | 'last_evaluated_at' | 'incident_count'>> & { name: string }
export interface Incident {
  id: string; rule_id: string; rule_name: string; analysis_id: string; analysis_name: string | null; feature_id: string
  severity: Severity; category: string; status: IncidentStatus; title: string; message: string
  evidence: { rule: Record<string, unknown>; matched: Record<string, unknown>; analysis: Record<string, unknown>; notice?: string }
  area_m2: number | null; confidence: number | null; centroid: Position | null; bbox: BBox | null; region_id: string | null
  detected_at: string; created_at: string; acknowledged_at: string | null; resolved_at: string | null
  resolution_note: string | null; is_demo: boolean
}
export interface IncidentPage { total: number; open: number; limit: number; offset: number; items: Incident[] }

// ---------------------------------------------------------------------------------------------- regions
export interface Region {
  id: string; name: string; description: string | null; geometry: GeoJSONGeometry | null
  center_lat: number; center_lng: number; area_km2: number; risk_level: string; created_at: string
}

// ---------------------------------------------------------------------------------------------- system / layers
export interface ModelCard {
  id: string; name: string; dataset: string; category: string; description: string; architecture: string
  threshold: number; trained_gsd_m: number; available: boolean; limitations: string[]
  metrics: { test?: { precision: number; recall: number; f1: number; change_iou: number; num_samples: number }; val?: Record<string, number> }
  metrics_note: string
}
export interface ProviderStatus { provider: string; configured: boolean; catalog: string; imagery: string; detail: string }
export interface SystemStatus {
  version: string; env: string; demo_mode: boolean; database: { ok: boolean; error: string | null }; storage: { ok: boolean }
  job_runner: string; job_concurrency: number
  ml: { code_available: boolean; torch: boolean; cuda: boolean; device: string | null; default_model: string | null; models: ModelCard[]; any_model_ready: boolean }
  sentinel: ProviderStatus[]; llm: { configured: boolean; provider: string }
  limits: { max_upload_mb: number; max_raster_pixels: number; max_aoi_km2: number }
}

// ---------------------------------------------------------------------------------------------- analytics
export interface Reference { kind: 'feature' | 'analysis' | 'region'; id: string; label: string; centroid?: Position | null; analysis_id?: string | null }
export interface AnalyticsAnswer {
  question: string | null; interpreted_as: Record<string, unknown>; operation: string; understood: boolean
  data: Record<string, unknown>; answer: string; answer_source: 'deterministic' | 'llm_narration'
  measured_facts: string[]; caveats: string[]; references: Reference[]; suggestions: string[]
}
