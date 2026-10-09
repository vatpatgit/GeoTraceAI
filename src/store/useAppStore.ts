import { create } from 'zustand'
import type { MlChangeCollection } from '@/lib/api/sentinel'
import type { WeatherAlert } from '@/lib/api/weather'
import type { Analysis, BBox, FeatureCollectionLite, FeatureFilters, Position, Project, Region, Severity, SystemStatus } from '@/lib/api'
import type { LayerInfo } from '@/lib/api/layers'
import { type Role, normalizeRole } from '@/lib/auth'

export type ViewMode = 'globe' | 'map' | 'compare'
export type DrawerTab = 'detections' | 'progress' | 'stats' | 'downloads'
export type PanelId = 'layers' | 'analyses' | 'search' | 'quick' | null

export interface AuthUser { id: string; email: string; name: string; role: Role }
export interface Camera { center: Position; zoom: number; bearing: number; pitch: number }
export interface FlyRequest { id: number; bbox?: BBox; center?: Position; zoom?: number }
export interface LayerState { visible: boolean; opacity: number; loading?: boolean; error?: string | null }
export interface QuickScene { url: string; date: string; cloud: number | null; productId: string; /** display name when there is no meaningful date (uploaded file) */ label?: string }
/** Where a quick comparison came from, so the ML switch / save action call the right backend route. */
export type QuickSource = { kind: 'sentinel' } | { kind: 'upload'; beforeAssetId: string; afterAssetId: string; projectId: string }
/** Two Sentinel-2 images of one box for two dates, retrieved on demand and drawn georeferenced in 2D / compare / 3D. */
export interface QuickCompare { bbox: BBox; before: QuickScene; after: QuickScene; source?: QuickSource }
export interface QuickChanges { show: boolean; status: 'idle' | 'loading' | 'ready' | 'error'; error: string | null; data: MlChangeCollection | null }
export const NO_QUICK_CHANGES: QuickChanges = { show: false, status: 'idle', error: null, data: null }
/** An ordinary (non-georeferenced) image kept in the browser; the file is sent only to the ML endpoint. */
export interface PlainImage { file: File; url: string; name: string; width: number; height: number }
export interface PlainCompare { before: PlainImage; after: PlainImage }
export interface Toast { id: number; kind: 'info' | 'success' | 'error'; text: string }

export interface ActiveFilters {
  severities: Severity[]
  categories: string[]
  reviewStatus: ('unreviewed' | 'confirmed' | 'rejected')[]
  minAreaM2: number | null
  search: string
}
export const EMPTY_FILTERS: ActiveFilters = { severities: [], categories: [], reviewStatus: [], minAreaM2: null, search: '' }

/** Server-side feature filters derived from the UI filters (the same object drives list, map layer, globe and exports). */
export function toFeatureFilters(f: ActiveFilters): FeatureFilters {
  return {
    severity: f.severities.length ? f.severities : undefined,
    category: f.categories.length ? f.categories : undefined,
    review_status: f.reviewStatus.length ? f.reviewStatus : undefined,
    min_area_m2: f.minAreaM2 ?? undefined,
  }
}
export const hasActiveFilters = (f: ActiveFilters): boolean =>
  !!(f.severities.length || f.categories.length || f.reviewStatus.length || f.minAreaM2 !== null)

/** Fixed (client-owned) change-intelligence layers; environmental/risk layers come from the backend catalogue. */
export const CHANGE_LAYERS: { id: string; name: string; defaultVisible: boolean; defaultOpacity: number; description: string }[] = [
  { id: 'change-polygons', name: 'Change polygons', defaultVisible: true, defaultOpacity: 0.85, description: 'Detected change features, styled by severity' },
  { id: 'aoi', name: 'AOI / monitored boundaries', defaultVisible: true, defaultOpacity: 1, description: 'Analysis footprint and monitored regions' },
  { id: 'imagery-after', name: 'After imagery', defaultVisible: true, defaultOpacity: 1, description: 'Aligned "after" raster of the active analysis' },
  { id: 'imagery-before', name: 'Before imagery', defaultVisible: false, defaultOpacity: 1, description: 'Aligned "before" raster of the active analysis' },
  { id: 'change-score', name: 'Change score heat-map', defaultVisible: false, defaultOpacity: 0.7, description: 'Per-pixel change score (0-1) used for detection' },
  { id: 'delta-ndvi', name: 'dNDVI (loss / gain)', defaultVisible: false, defaultOpacity: 0.8, description: 'NDVI difference; needs red + NIR bands' },
  { id: 'weather-alerts', name: 'Weather alerts (provider)', defaultVisible: true, defaultOpacity: 0.45, description: 'OpenWeather alert areas for your AOIs. Not satellite-derived and not the extent of damage' },
]

interface AppState {
  // ---- auth
  authStatus: 'loading' | 'authenticated' | 'unauthenticated'
  authUser: AuthUser | null
  setAuthUser: (user: AuthUser | null) => void
  setAuthStatus: (s: AppState['authStatus']) => void
  signOut: () => void

  // ---- workspace
  system: SystemStatus | null
  systemError: string | null
  setSystem: (s: SystemStatus | null, error?: string | null) => void
  regions: Region[]
  setRegions: (r: Region[]) => void
  projects: Project[]
  activeProjectId: string | null
  setProjects: (p: Project[]) => void
  setActiveProject: (id: string | null) => void
  analyses: Analysis[]
  setAnalyses: (a: Analysis[]) => void
  upsertAnalysis: (a: Analysis) => void
  activeAnalysisId: string | null
  /** Activate an analysis: resets selection/filters and requests the camera to fit its footprint. */
  setActiveAnalysis: (id: string | null) => void

  // ---- shared geographic state (globe + 2D map + compare read the same values)
  viewMode: ViewMode
  setViewMode: (m: ViewMode) => void
  camera: Camera
  setCamera: (c: Partial<Camera>) => void
  flyRequest: FlyRequest | null
  requestFly: (r: Omit<FlyRequest, 'id'>) => void
  selectedFeatureId: string | null
  hoveredFeatureId: string | null
  /** Select a detection; with `fly` the active renderer centres on it. */
  selectFeature: (id: string | null, opts?: { fly?: boolean; center?: Position; bbox?: BBox }) => void
  setHoveredFeature: (id: string | null) => void
  filters: ActiveFilters
  setFilters: (f: Partial<ActiveFilters>) => void
  resetFilters: () => void
  comparePosition: number
  setComparePosition: (p: number) => void
  /** bumps when features were re-fetched / reviewed so renderers refresh */
  featuresVersion: number
  bumpFeatures: () => void
  /** the feature collection (post server-side filtering) that globe, 2D map and compare all render */
  featureData: { analysisId: string | null; status: 'idle' | 'loading' | 'ready' | 'error'; error: string | null; fc: FeatureCollectionLite | null }
  setFeatureData: (d: Partial<AppState['featureData']>) => void

  // ---- layers
  layerCatalog: LayerInfo[]
  setLayerCatalog: (l: LayerInfo[]) => void
  layerState: Record<string, LayerState>
  setLayerVisible: (id: string, visible: boolean) => void
  setLayerOpacity: (id: string, opacity: number) => void
  setLayerStatus: (id: string, patch: Partial<LayerState>) => void
  basemap: 'satellite' | 'dark'
  setBasemap: (b: 'satellite' | 'dark') => void

  // ---- ui
  leftPanel: PanelId
  setLeftPanel: (p: PanelId) => void
  /** which layer group the sidebar entry asked the layer panel to scroll to */
  layerFocus: 'environmental' | 'risk' | null
  rightPanelOpen: boolean
  setRightPanelOpen: (o: boolean) => void
  drawerOpen: boolean
  drawerHeight: number
  drawerTab: DrawerTab
  setDrawerOpen: (o: boolean) => void
  setDrawerHeight: (h: number) => void
  setDrawerTab: (t: DrawerTab) => void
  quickCompare: QuickCompare | null
  setQuickCompare: (q: QuickCompare | null) => void
  weatherAlerts: WeatherAlert[]
  setWeatherAlerts: (a: WeatherAlert[]) => void
  selectedWeatherId: string | null
  selectWeather: (id: string | null, opts?: { fly?: boolean }) => void
  drawMode: boolean
  setDrawMode: (on: boolean) => void
  drawnBox: BBox | null
  setDrawnBox: (b: BBox | null) => void
  plainCompare: PlainCompare | null
  setPlainCompare: (p: PlainCompare | null) => void
  quickChanges: QuickChanges
  setQuickChanges: (c: Partial<QuickChanges>) => void
  quickPrefill: { name: string; bbox: BBox } | null
  setQuickPrefill: (p: { name: string; bbox: BBox } | null) => void
  quickShow: 'before' | 'after'
  setQuickShow: (v: 'before' | 'after') => void
  toasts: Toast[]
  toast: (kind: Toast['kind'], text: string) => void
  dismissToast: (id: number) => void
}

const defaultCamera: Camera = { center: [10, 25], zoom: 1.6, bearing: 0, pitch: 0 }
let flySeq = 0
let toastSeq = 0

function defaultLayerState(): Record<string, LayerState> {
  const s: Record<string, LayerState> = {}
  for (const l of CHANGE_LAYERS) s[l.id] = { visible: l.defaultVisible, opacity: l.defaultOpacity }
  return s
}

export const useAppStore = create<AppState>((set, get) => ({
  authStatus: 'loading',
  authUser: null,
  setAuthUser: (user) => set({ authUser: user, authStatus: user ? 'authenticated' : 'unauthenticated' }),
  setAuthStatus: (authStatus) => set({ authStatus }),
  signOut: () => set({
    authUser: null, authStatus: 'unauthenticated', projects: [], analyses: [], activeAnalysisId: null, activeProjectId: null,
    selectedFeatureId: null, system: null,
  }),

  system: null,
  systemError: null,
  setSystem: (system, error = null) => set({ system, systemError: error }),
  regions: [],
  setRegions: (regions) => set({ regions }),
  projects: [],
  activeProjectId: null,
  setProjects: (projects) => set((st) => ({
    projects,
    activeProjectId: st.activeProjectId && projects.some((p) => p.id === st.activeProjectId) ? st.activeProjectId : projects[0]?.id ?? null,
  })),
  setActiveProject: (activeProjectId) => set({ activeProjectId }),
  analyses: [],
  setAnalyses: (analyses) => set({ analyses }),
  upsertAnalysis: (a) => set((st) => {
    const i = st.analyses.findIndex((x) => x.id === a.id)
    const analyses = i === -1 ? [a, ...st.analyses] : st.analyses.map((x) => (x.id === a.id ? a : x))
    return { analyses }
  }),
  activeAnalysisId: null,
  setActiveAnalysis: (id) => {
    const a = id ? get().analyses.find((x) => x.id === id) : null
    set({
      activeAnalysisId: id, selectedFeatureId: null, hoveredFeatureId: null, filters: EMPTY_FILTERS, comparePosition: 0.5,
      featuresVersion: get().featuresVersion + 1,
    })
    if (a?.bounds) get().requestFly({ bbox: a.bounds })
  },

  viewMode: 'map',
  setViewMode: (viewMode) => set({ viewMode }),
  camera: defaultCamera,
  setCamera: (c) => set((st) => ({ camera: { ...st.camera, ...c } })),
  flyRequest: null,
  requestFly: (r) => set({ flyRequest: { ...r, id: ++flySeq } }),
  selectedFeatureId: null,
  hoveredFeatureId: null,
  selectFeature: (id, opts) => {
    set({ selectedFeatureId: id, ...(id ? { rightPanelOpen: true } : {}) })
    if (id && opts?.fly) get().requestFly({ center: opts.center, bbox: opts.bbox, zoom: opts.bbox ? undefined : 15 })
  },
  setHoveredFeature: (hoveredFeatureId) => set({ hoveredFeatureId }),
  filters: EMPTY_FILTERS,
  setFilters: (f) => set((st) => ({ filters: { ...st.filters, ...f }, featuresVersion: st.featuresVersion + 1 })),
  resetFilters: () => set((st) => ({ filters: EMPTY_FILTERS, featuresVersion: st.featuresVersion + 1 })),
  comparePosition: 0.5,
  setComparePosition: (comparePosition) => set({ comparePosition: Math.max(0, Math.min(1, comparePosition)) }),
  featuresVersion: 0,
  bumpFeatures: () => set((st) => ({ featuresVersion: st.featuresVersion + 1 })),
  featureData: { analysisId: null, status: 'idle', error: null, fc: null },
  setFeatureData: (d) => set((st) => ({ featureData: { ...st.featureData, ...d } })),

  layerCatalog: [],
  setLayerCatalog: (layerCatalog) => set((st) => {
    const next = { ...st.layerState }
    for (const l of layerCatalog) {
      if (!next[l.id]) next[l.id] = { visible: false, opacity: l.default_opacity }
    }
    return { layerCatalog, layerState: next }
  }),
  layerState: defaultLayerState(),
  setLayerVisible: (id, visible) => set((st) => ({ layerState: { ...st.layerState, [id]: { ...(st.layerState[id] ?? { opacity: 0.7 }), visible } } })),
  setLayerOpacity: (id, opacity) => set((st) => ({
    layerState: { ...st.layerState, [id]: { ...(st.layerState[id] ?? { visible: false }), opacity: Math.max(0, Math.min(1, opacity)) } },
  })),
  setLayerStatus: (id, patch) => set((st) => ({ layerState: { ...st.layerState, [id]: { ...(st.layerState[id] ?? { visible: false, opacity: 0.7 }), ...patch } } })),
  basemap: 'satellite',
  setBasemap: (basemap) => set({ basemap }),

  leftPanel: null,
  setLeftPanel: (leftPanel) => set({ leftPanel }),
  layerFocus: null,
  rightPanelOpen: true,
  setRightPanelOpen: (rightPanelOpen) => set({ rightPanelOpen }),
  drawerOpen: true,
  drawerHeight: 260,
  drawerTab: 'detections',
  setDrawerOpen: (drawerOpen) => set({ drawerOpen }),
  setDrawerHeight: (h) => set({ drawerHeight: Math.max(120, Math.min(560, h)) }),
  setDrawerTab: (drawerTab) => set({ drawerTab, drawerOpen: true }),
  quickCompare: null,
  setQuickCompare: (q) => set((st) => {
    if (st.quickCompare) { URL.revokeObjectURL(st.quickCompare.before.url); URL.revokeObjectURL(st.quickCompare.after.url) }
    return { quickCompare: q, quickChanges: NO_QUICK_CHANGES, ...(q ? { quickShow: 'after' as const } : {}) }
  }),
  weatherAlerts: [],
  setWeatherAlerts: (weatherAlerts) => set((st) => ({ weatherAlerts, selectedWeatherId: weatherAlerts.some((a) => a.id === st.selectedWeatherId) ? st.selectedWeatherId : null })),
  selectedWeatherId: null,
  selectWeather: (id, opts) => {
    set({ selectedWeatherId: id })
    const a = id ? get().weatherAlerts.find((x) => x.id === id) : null
    if (a?.geometry && opts?.fly) {
      const pts: number[][] = []
      const walk = (c: unknown): void => { if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[]); else if (Array.isArray(c)) c.forEach(walk) }
      walk((a.geometry as { coordinates?: unknown }).coordinates)
      if (pts.length) {
        const xs = pts.map((p) => p[0]); const ys = pts.map((p) => p[1])
        const pad = pts.length === 1 ? 0.05 : 0
        get().requestFly({ bbox: [Math.min(...xs) - pad, Math.min(...ys) - pad, Math.max(...xs) + pad, Math.max(...ys) + pad] })
      }
    }
  },
  drawMode: false,
  setDrawMode: (drawMode) => set({ drawMode }),
  drawnBox: null,
  setDrawnBox: (drawnBox) => set({ drawnBox }),
  plainCompare: null,
  setPlainCompare: (p) => set((st) => {
    if (st.plainCompare && st.plainCompare !== p) { URL.revokeObjectURL(st.plainCompare.before.url); URL.revokeObjectURL(st.plainCompare.after.url) }
    return { plainCompare: p }
  }),
  quickChanges: NO_QUICK_CHANGES,
  setQuickChanges: (c) => set((st) => ({ quickChanges: { ...st.quickChanges, ...c } })),
  quickPrefill: null,
  setQuickPrefill: (quickPrefill) => set({ quickPrefill }),
  quickShow: 'after',
  setQuickShow: (quickShow) => set({ quickShow }),
  toasts: [],
  toast: (kind, text) => {
    const id = ++toastSeq
    set((st) => ({ toasts: [...st.toasts.slice(-3), { id, kind, text }] }))
    if (typeof window !== 'undefined') setTimeout(() => get().dismissToast(id), kind === 'error' ? 8000 : 4000)
  },
  dismissToast: (id) => set((st) => ({ toasts: st.toasts.filter((t) => t.id !== id) })),
}))

export function toAuthUser(me: { id: string; email: string; name: string; role: string }): AuthUser {
  return { id: me.id, email: me.email, name: me.name, role: normalizeRole(me.role) }
}

export const selectActiveAnalysis = (s: AppState): Analysis | null => s.analyses.find((a) => a.id === s.activeAnalysisId) ?? null
