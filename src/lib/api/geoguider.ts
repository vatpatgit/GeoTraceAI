/** GeoGuider API types. Blocks are structured result cards produced by the backend from real tool outputs. */

export type GgState = 'IDLE' | 'INTENT_RESOLVED' | 'AOI_CONFIRMED' | 'SCENES_FOUND' | 'SCENES_SELECTED' | 'PREPROCESSING' | 'ANALYZING' | 'RESULTS_READY' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export interface GgOption { id: string; label: string; description?: string | null }
export interface GgPending { id: string; kind: string; prompt: string; options: GgOption[] }
export interface GgJob { id: string; name?: string; status: string; progress: number; stage: string | null; error: string | null }

export interface GgScene {
  product_id: string; acquired_at: string; cloud_cover_pct: number | null; coverage_of_aoi_pct: number | null
  platform?: string | null; resolution_m?: number | null; provider?: string
}
export interface GgPairOption { id: string; kind: 'two_date' | 'series'; recommended: boolean; pairs: { before: GgScene; after: GgScene; seasonal_gap_days: number; separation_days: number }[] }
export interface GgResultSections { observed: string[]; computed: string[]; predictions: string[]; interpretation: string[]; limitations: string[] }

export type GgBlock =
  | { type: 'choices'; pending_id: string; kind: string; prompt: string; options: GgOption[] }
  | { type: 'aoi'; aoi: { id: string; name: string; bbox: number[]; area_km2: number } }
  | { type: 'coverage'; provider: string; max_cloud: number; rows: { start: string; end: string; count: number; best_cloud: number | null; failed: boolean; truncated: boolean }[] }
  | { type: 'scene_pairs'; options: GgPairOption[] }
  | { type: 'scene_list'; scenes: GgScene[] }
  | { type: 'plan'; rows: [string, string][] }
  | { type: 'progress'; analysis_ids: string[] }
  | { type: 'period_summary'; rows: [string, number, string][] }
  | { type: 'result'; analysis_id: string; name: string; headline: string; model_id: string | null; feature_count: number; changed_area_m2: number; sections: GgResultSections }
  | { type: 'facts'; facts: string[]; caveats: string[]; source: string }
  | { type: 'weather'; alerts: { id: string; title: string; severity: string; source: string | null; start: string | null; end: string | null }[]; configured: boolean; aoi: string }
  | { type: 'export'; items: { analysis_id: string; format: string; feature_count: number; path: string; name: string }[] }
  | { type: 'error'; code: string; message: string; retryable: boolean }

export type GgAction =
  | { type: 'navigate'; route: string; panel?: string | null }
  | { type: 'show_aoi'; bbox: number[]; aoi_id: string; name: string }
  | { type: 'open_analysis'; analysis_id: string }
  | { type: 'track_analyses'; analysis_ids: string[] }
  | { type: 'zoom_to'; center: number[]; label?: string }
  | { type: 'show_weather' }
  | { type: 'download_export'; path: string; format: string; name: string }
  | { type: 'start_draw' }

export interface GgMessage { id: string; role: 'user' | 'assistant'; content: string; blocks: GgBlock[]; actions: GgAction[]; created_at: string }
export interface GgWorkflow {
  conversation_id: string; state: GgState; pending: GgPending | null; job_ids: string[]; jobs: GgJob[]; cancellable: boolean
  aoi: { id: string; name: string; bbox: number[]; area_km2: number } | null; period: { start: string; end: string; label: string } | null; error: string | null
}
export interface GgChatResponse { conversation_id: string; messages: GgMessage[]; workflow: GgWorkflow; suggestions: string[] }
export interface GgStatus {
  enabled: boolean; llm: { configured: boolean; provider: string | null; mode: 'llm' | 'rules'; note: string | null }
  geocoder: { configured: boolean }; satellite: { catalogue: boolean; imagery: boolean }; weather: { configured: boolean }; model: { id: string; ready: boolean }
  capabilities: Record<string, boolean>
}
export interface GgConversation { id: string; title: string; updated_at: string; messages: GgMessage[]; workflow: GgWorkflow | null }
export interface GgUi { page?: string; active_analysis_id?: string | null; drawn_bbox?: number[] | null }
