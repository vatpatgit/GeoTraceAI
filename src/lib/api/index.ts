import { API_BASE, ApiError, apiFetch, authHeaders, downloadFile, getToken, parseErrorBody, setToken } from './client'
import type {
  AlertRule, AlertRuleInput, Analysis, AnalysisCreate, AnalysisEvent, AnalyticsAnswer, Aoi, AoiCreate, ChangeFeature,
  ExportFormat, FeatureCollectionLite, FeatureFilters, FeaturePage, ImageryAsset, Incident, IncidentPage, IncidentStatus,
  PairValidation, Project, Region, ReviewStatus, SystemStatus, UserMe,
} from './types'
import type { LayerInfo } from './layers'
import type { AoiWeatherState, WeatherAlertList, WeatherEvent, WeatherRefresh, WeatherStatus } from './weather'
import type { SentinelSearchBody, SentinelSearchResult, AcquireBody, AcquireResult, MlChangeCollection, PlainChangeCollection } from './sentinel'

export * from './client'
export * from './types'
export * from './layers'
export * from './sentinel'
export * from './weather'

/** Flatten FeatureFilters into query params (arrays are repeated, bbox is comma separated). */
export function filterQuery(f: FeatureFilters = {}): Record<string, string | number | (string | number)[] | undefined> {
  return {
    severity: f.severity, category: f.category, review_status: f.review_status,
    min_area_m2: f.min_area_m2, max_area_m2: f.max_area_m2, min_confidence: f.min_confidence, min_magnitude: f.min_magnitude,
    bbox: f.bbox?.join(','), ids: f.ids, sort: f.sort,
  }
}

export const api = {
  // ------------------------------------------------------------------------------------------------ auth
  async login(email: string, password: string): Promise<string> {
    // FastAPI OAuth2 password form (the same endpoint Swagger uses)
    let res: Response
    try {
      res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password }).toString(),
      })
    } catch {
      throw new ApiError(0, 'Cannot reach the GeoTrace backend. Check that the API is running.', 'network')
    }
    if (!res.ok) {
      let msg = 'Invalid email or password.'
      try { msg = parseErrorBody(res.status, await res.json()).message } catch { /* keep default */ }
      throw new ApiError(res.status, res.status === 401 ? 'Invalid email or password.' : msg)
    }
    const data = (await res.json()) as { access_token: string }
    setToken(data.access_token)
    return data.access_token
  },
  logout(): void { setToken(null) },
  me: () => apiFetch<UserMe>('/auth/me'),
  hasToken: () => !!getToken(),

  // ------------------------------------------------------------------------------------------------ system
  systemStatus: () => apiFetch<SystemStatus>('/system/status'),

  // ------------------------------------------------------------------------------------------------ projects & AOIs
  projects: {
    list: () => apiFetch<Project[]>('/projects'),
    ensureDefault: () => apiFetch<Project>('/projects/default', { method: 'POST' }),
    create: (body: { name: string; description?: string; visibility?: 'private' | 'shared' }) => apiFetch<Project>('/projects', { method: 'POST', body }),
    update: (id: string, body: Partial<{ name: string; description: string; visibility: 'private' | 'shared' }>) => apiFetch<Project>(`/projects/${id}`, { method: 'PATCH', body }),
    remove: (id: string) => apiFetch<void>(`/projects/${id}`, { method: 'DELETE' }),
    aois: (id: string) => apiFetch<Aoi[]>(`/projects/${id}/aois`),
    createAoi: (id: string, body: AoiCreate) => apiFetch<Aoi>(`/projects/${id}/aois`, { method: 'POST', body }),
    removeAoi: (id: string, aoiId: string) => apiFetch<void>(`/projects/${id}/aois/${aoiId}`, { method: 'DELETE' }),
  },

  // ------------------------------------------------------------------------------------------------ imagery
  imagery: {
    list: (projectId: string) => apiFetch<ImageryAsset[]>('/imagery', { query: { project_id: projectId } }),
    get: (id: string) => apiFetch<ImageryAsset>(`/imagery/${id}`),
    update: (id: string, body: Partial<{ band_map: Record<string, number>; acquisition_start: string | null; acquisition_end: string | null }>) =>
      apiFetch<ImageryAsset>(`/imagery/${id}`, { method: 'PATCH', body }),
    remove: (id: string) => apiFetch<void>(`/imagery/${id}`, { method: 'DELETE' }),
    validatePair: (body: { before_asset_id: string; after_asset_id: string; aoi_id?: string | null; band_map?: Record<string, number> | null }) =>
      apiFetch<PairValidation>('/imagery/validate-pair', { method: 'POST', body }),
    /** One georeferenced PNG of an uploaded asset over a lon/lat box (object URL; the caller revokes it). Both dates use the same box => same pixel grid. */
    async renderPng(id: string, bbox: [number, number, number, number], width = 1536): Promise<string> {
      let res: Response
      try { res = await fetch(`${API_BASE}/imagery/${id}/render?bbox=${bbox.join(',')}&width=${width}`, { headers: authHeaders() }) }
      catch { throw new ApiError(0, 'Cannot reach the GeoTrace backend. Check that the API is running.', 'network') }
      if (!res.ok) {
        let p = { message: `Rendering failed (${res.status}).` }
        try { p = parseErrorBody(res.status, await res.json()) } catch { /* non-JSON */ }
        throw new ApiError(res.status, p.message)
      }
      return URL.createObjectURL(await res.blob())
    },
    /** Learned change detection between two uploaded images over a common box (GeoJSON + statistics). */
    mlChanges: (body: { before_asset_id: string; after_asset_id: string; bbox: [number, number, number, number]; width?: number; model_id?: string }) =>
      apiFetch<MlChangeCollection>('/imagery/ml-changes', { method: 'POST', body }),
    /** ML change detection between two ordinary images (PNG/JPEG/WebP/BMP/GIF); nothing is stored server-side. */
    async plainMlChanges(before: File, after: File, opts: { pixelSizeM?: number | null; signal?: AbortSignal } = {}): Promise<PlainChangeCollection> {
      const form = new FormData()
      form.append('before', before)
      form.append('after', after)
      if (opts.pixelSizeM) form.append('pixel_size_m', String(opts.pixelSizeM))
      return apiFetch<PlainChangeCollection>('/imagery/plain-ml-changes', { method: 'POST', body: form, signal: opts.signal })
    },
    /** Multipart upload with progress (fetch cannot report upload progress). */
    upload(file: File, projectId: string, opts: { acquisitionDate?: string; bandMap?: Record<string, number>; onProgress?: (fraction: number) => void; signal?: AbortSignal } = {}): Promise<ImageryAsset> {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', `${API_BASE}/imagery/upload`)
        const token = getToken()
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
        xhr.upload.onprogress = (e) => { if (e.lengthComputable) opts.onProgress?.(e.loaded / e.total) }
        xhr.onerror = () => reject(new ApiError(0, 'Cannot reach the GeoTrace backend. Check that the API is running.', 'network'))
        xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
        xhr.onload = () => {
          let body: unknown = null
          try { body = JSON.parse(xhr.responseText) } catch { /* non-JSON */ }
          if (xhr.status >= 200 && xhr.status < 300) return resolve(body as ImageryAsset)
          const p = parseErrorBody(xhr.status, body)
          reject(new ApiError(xhr.status, p.message, p.code, p.details, xhr.getResponseHeader('x-request-id')))
        }
        opts.signal?.addEventListener('abort', () => xhr.abort())
        const form = new FormData()
        form.append('file', file)
        form.append('project_id', projectId)
        if (opts.acquisitionDate) form.append('acquisition_date', opts.acquisitionDate)
        if (opts.bandMap) form.append('band_map', JSON.stringify(opts.bandMap))
        xhr.send(form)
      })
    },
  },

  // ------------------------------------------------------------------------------------------------ analyses
  analyses: {
    create: (body: AnalysisCreate) => apiFetch<Analysis>('/analyses', { method: 'POST', body }),
    list: (q: { project_id?: string; status?: string; limit?: number; offset?: number } = {}) => apiFetch<Analysis[]>('/analyses', { query: q }),
    get: (id: string) => apiFetch<Analysis>(`/analyses/${id}`),
    events: (id: string) => apiFetch<AnalysisEvent[]>(`/analyses/${id}/events`),
    cancel: (id: string) => apiFetch<Analysis>(`/analyses/${id}/cancel`, { method: 'POST' }),
    retry: (id: string) => apiFetch<Analysis>(`/analyses/${id}/retry`, { method: 'POST' }),
    remove: (id: string) => apiFetch<void>(`/analyses/${id}`, { method: 'DELETE' }),
    features: (id: string, filters: FeatureFilters = {}, page: { limit?: number; offset?: number } = {}) =>
      apiFetch<FeaturePage>(`/analyses/${id}/features`, { query: { ...filterQuery(filters), ...page } }),
    featuresGeoJSON: (id: string, filters: FeatureFilters = {}, limit = 5000, signal?: AbortSignal) =>
      apiFetch<FeatureCollectionLite>(`/analyses/${id}/features`, { query: { ...filterQuery(filters), format: 'geojson', limit }, signal }),
    feature: (id: string, featureId: string) => apiFetch<ChangeFeature>(`/analyses/${id}/features/${featureId}`),
    review: (id: string, featureId: string, review_status: ReviewStatus, review_note?: string) =>
      apiFetch<ChangeFeature>(`/analyses/${id}/features/${featureId}/review`, { method: 'PATCH', body: { review_status, review_note } }),
    /** Download exactly the features matching `filters` (or the `ids` selection) in the requested format. */
    export: (id: string, format: ExportFormat, filters: FeatureFilters = {}) =>
      filters.ids && filters.ids.length > 25
        ? downloadFile(`/analyses/${id}/export`, { method: 'POST', body: { format, filters } }, `geotrace.${format}`)
        : downloadFile(`/analyses/${id}/export`, { query: { format, ...filterQuery(filters) } }, `geotrace.${format}`),
    downloadArtifact: (id: string, name: string) => downloadFile(`/analyses/${id}/artifacts/${name}`, {}, `${name}.tif`),
    evaluateAlerts: (id: string) => apiFetch<{ incidents_created: number; rules_evaluated: number; suppressed_duplicates: number }>(`/analyses/${id}/evaluate-alerts`, { method: 'POST' }),
  },

  // ------------------------------------------------------------------------------------------------ alerts
  alerts: {
    rules: () => apiFetch<AlertRule[]>('/alerts/rules'),
    createRule: (body: AlertRuleInput) => apiFetch<AlertRule>('/alerts/rules', { method: 'POST', body }),
    updateRule: (id: string, body: Partial<AlertRuleInput>) => apiFetch<AlertRule>(`/alerts/rules/${id}`, { method: 'PATCH', body }),
    deleteRule: (id: string) => apiFetch<void>(`/alerts/rules/${id}`, { method: 'DELETE' }),
    incidents: (q: { status?: string[]; severity?: string[]; category?: string[]; rule_id?: string; analysis_id?: string; region_id?: string; since?: string; until?: string; limit?: number; offset?: number } = {}) =>
      apiFetch<IncidentPage>('/alerts', { query: q as Record<string, string | number | (string | number)[] | undefined> }),
    stats: () => apiFetch<{ by_status: Record<string, number>; unresolved_by_severity: Record<string, number>; unresolved: number }>('/alerts/stats'),
    setStatus: (id: string, status: IncidentStatus, resolution_note?: string) =>
      apiFetch<Incident>(`/alerts/${id}`, { method: 'PATCH', body: { status, resolution_note } }),
  },

  // ------------------------------------------------------------------------------------------------ regions
  regions: {
    list: async (): Promise<Region[]> => (await apiFetch<{ regions: Region[]; total: number }>('/regions/')).regions,
  },

  // ------------------------------------------------------------------------------------------------ sentinel (Phase 5)
  sentinel: {
    search: (body: SentinelSearchBody) => apiFetch<SentinelSearchResult>('/sentinel/search', { method: 'POST', body }),
    acquire: (body: AcquireBody) => apiFetch<AcquireResult>('/sentinel/acquire', { method: 'POST', body }),
    /** Run the learned model on two retrieved images of one box; returns changed areas as GeoJSON. */
    mlChanges: (body: { bbox: [number, number, number, number]; before_at: string; after_at: string; model_id?: string }) =>
      apiFetch<MlChangeCollection>('/sentinel/ml-changes', { method: 'POST', body }),
  },

  // ------------------------------------------------------------------------------------------------ weather alerts (provider key stays on the server)
  weather: {
    status: () => apiFetch<WeatherStatus>('/weather-alerts/status'),
    list: (q: { aoi_id?: string; status?: 'active' | 'expired' } = {}) => apiFetch<WeatherAlertList>('/weather-alerts', { query: q }),
    refresh: (body: { aoi_id: string; force?: boolean; source?: string; tags?: string[]; lookahead_hours?: number }) =>
      apiFetch<WeatherRefresh>('/weather-alerts/refresh', { method: 'POST', body }),
    setMonitoring: (aoiId: string, enabled: boolean) => apiFetch<AoiWeatherState>(`/weather-alerts/aois/${aoiId}/monitoring`, { method: 'PATCH', body: { enabled } }),
    events: (unread = false) => apiFetch<WeatherEvent[]>('/weather-alerts/events', { query: { unread } }),
    markRead: (body: { ids?: string[]; all?: boolean }) => apiFetch<{ marked_read: number }>('/weather-alerts/events/read', { method: 'POST', body }),
  },

  // ------------------------------------------------------------------------------------------------ layers / analytics
  layers: {
    list: () => apiFetch<LayerInfo[]>('/layers'),
  },
  reports: {
    download: (analysisId: string, format: 'json' | 'csv' | 'pdf') =>
      downloadFile(`/reports/analyses/${analysisId}`, { query: { format } }, `geotrace_report.${format}`),
  },
  analytics: {
    query: (body: { question?: string; spec?: Record<string, unknown>; analysis_id?: string; project_id?: string; narrate?: boolean }) =>
      apiFetch<AnalyticsAnswer>('/analytics/query', { method: 'POST', body }),
    overview: (q: { project_id?: string } = {}) => apiFetch<Record<string, unknown>>('/analytics/overview', { query: q }),
  },
}
