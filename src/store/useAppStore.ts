import { create } from 'zustand'
import type { UserRole, ViewMode, MapViewState, AlertConfig, DateRange } from '@/types'
import type { LayerVisibilityState } from '@/types/layers'
import { getDefaultLayerVisibility } from '@/services/maps/layerManager'

interface AuthUser {
  id: string
  email: string
  name: string
  role: UserRole
}

interface AppState {
  // Auth
  authStatus: 'loading' | 'authenticated' | 'unauthenticated'
  setAuthStatus: (status: AppState['authStatus']) => void
  authUser: AuthUser | null
  setAuthUser: (user: AuthUser | null) => void
  userRole: UserRole
  setUserRole: (role: UserRole) => void

  // Map state
  mapView: MapViewState
  setMapView: (view: Partial<MapViewState>) => void
  setViewMode: (mode: ViewMode) => void
  updateMapCenter: (center: [number, number]) => void
  updateZoom: (zoom: number) => void
  setCurrentDate: (date: string) => void
  setDateRange: (range: DateRange) => void
  toggleLayer: (layer: 'satellite' | 'changeMask' | 'confidence') => void
  toggleComparisonMode: () => void

  // Layer visibility (new Layer Manager system)
  layerVisibility: LayerVisibilityState
  setLayerVisibility: (layerId: string, visible: boolean) => void
  setLayerOpacity: (layerId: string, opacity: number) => void

  // Selected date — authoritative timeline date for all dashboard consumers
  selectedDate: string

  // Region selection
  regions: import('@/types').Region[]
  regionsLoading: boolean
  regionsError: string | null
  setRegions: (regions: import('@/types').Region[]) => void
  setRegionsLoading: (loading: boolean) => void
  setRegionsError: (error: string | null) => void
  selectedRegion: string
  setSelectedRegion: (regionId: string) => void

  // Drawing mode
  isDrawing: boolean
  setIsDrawing: (drawing: boolean) => void
  drawnPolygon: number[][] | null
  setDrawnPolygon: (polygon: number[][] | null) => void

  // Analytics panel
  analyticsPanelOpen: boolean
  setAnalyticsPanelOpen: (open: boolean) => void

  // Modals
  alertConfigOpen: boolean
  setAlertConfigOpen: (open: boolean) => void
  reportDownloadOpen: boolean
  setReportDownloadOpen: (open: boolean) => void
  alertPanelOpen: boolean
  setAlertPanelOpen: (open: boolean) => void

  // Alert config
  alertConfig: AlertConfig
  setAlertConfig: (config: Partial<AlertConfig>) => void

  // Time slider
  isPlaying: boolean
  setIsPlaying: (playing: boolean) => void

  // Map click data
  clickedPoint: { lon: number; lat: number; confidence: number } | null
  setClickedPoint: (point: { lon: number; lat: number; confidence: number } | null) => void
}

const defaultDateRange: DateRange = {
  start: '2024-01-01',
  end: '2024-01-30',
}

const defaultMapView: MapViewState = {
  viewMode: 'globe',
  center: [-65.0, -2.5],
  zoom: 6,
  bearing: 0,
  pitch: 0,
  selectedRegion: '',
  currentDate: '2024-01-15',
  dateRange: defaultDateRange,
  activeLayers: {
    satellite: true,
    changeMask: true,
    confidence: false,
  },
  comparisonMode: false,
  comparisonDate: null,
}

export const useAppStore = create<AppState>((set, get) => ({
  // Auth
  authStatus: 'loading',
  setAuthStatus: (status) => set({ authStatus: status }),
  authUser: null,
  setAuthUser: (user) =>
    set((state) => ({
      authUser: user,
      authStatus: user ? 'authenticated' : 'unauthenticated',
      userRole: user?.role ?? state.userRole,
    })),
  userRole: 'Viewer',
  setUserRole: (role) =>
    set((state) => ({
      userRole: role,
      authUser: state.authUser ? { ...state.authUser, role } : state.authUser,
    })),

  // Map state
  mapView: defaultMapView,
  setMapView: (view) => set((state) => ({ mapView: { ...state.mapView, ...view } })),
  setViewMode: (mode) => set((state) => ({ mapView: { ...state.mapView, viewMode: mode } })),
  updateMapCenter: (center) =>
    set((state) => ({ mapView: { ...state.mapView, center } })),
  updateZoom: (zoom) => set((state) => ({ mapView: { ...state.mapView, zoom } })),
  setCurrentDate: (date) =>
    set((state) => ({ mapView: { ...state.mapView, currentDate: date }, selectedDate: date })),
  setDateRange: (range) =>
    set((state) => ({ mapView: { ...state.mapView, dateRange: range } })),
  toggleLayer: (layer) =>
    set((state) => ({
      mapView: {
        ...state.mapView,
        activeLayers: {
          ...state.mapView.activeLayers,
          [layer]: !state.mapView.activeLayers[layer],
        },
      },
    })),
  toggleComparisonMode: () =>
    set((state) => ({
      mapView: {
        ...state.mapView,
        comparisonMode: !state.mapView.comparisonMode,
        comparisonDate: !state.mapView.comparisonMode
          ? state.mapView.currentDate
          : null,
      },
    })),

  // Layer visibility (new Layer Manager system)
  layerVisibility: getDefaultLayerVisibility(),
  setLayerVisibility: (layerId, visible) =>
    set((state) => ({
      layerVisibility: {
        ...state.layerVisibility,
        [layerId]: {
          ...state.layerVisibility[layerId],
          visible,
        },
      },
    })),
  setLayerOpacity: (layerId, opacity) =>
    set((state) => ({
      layerVisibility: {
        ...state.layerVisibility,
        [layerId]: {
          ...state.layerVisibility[layerId],
          opacity: Math.max(0, Math.min(1, opacity)),
        },
      },
    })),

  // Selected date — synced with mapView.currentDate
  selectedDate: '2024-01-15',

  // Region selection — now also updates map center
  regions: [],
  regionsLoading: false,
  regionsError: null,
  setRegions: (regions) => set((state) => ({
    regions,
    selectedRegion: state.selectedRegion && regions.some((region) => region.id === state.selectedRegion)
      ? state.selectedRegion
      : regions[0]?.id ?? null,
    mapView: {
      ...state.mapView,
      selectedRegion: state.selectedRegion && regions.some((region) => region.id === state.selectedRegion)
        ? state.selectedRegion
        : regions[0]?.id ?? null,
    },
  })),
  setRegionsLoading: (loading) => set({ regionsLoading: loading }),
  setRegionsError: (error) => set({ regionsError: error }),
  selectedRegion: '',
  setSelectedRegion: (regionId) => {
    const region = get().regions.find((item) => item.id === regionId)
    const center: [number, number] = region
      ? [(region.bbox.minLon + region.bbox.maxLon) / 2, (region.bbox.minLat + region.bbox.maxLat) / 2]
      : defaultMapView.center
    set({
      selectedRegion: regionId,
      mapView: {
        ...defaultMapView,
        selectedRegion: regionId,
        center,
        zoom: region ? 5 : defaultMapView.zoom,
      },
    })
  },

  // Drawing mode
  isDrawing: false,
  setIsDrawing: (drawing) => set({ isDrawing: drawing }),
  drawnPolygon: null,
  setDrawnPolygon: (polygon) => set({ drawnPolygon: polygon }),

  // Analytics panel
  analyticsPanelOpen: true,
  setAnalyticsPanelOpen: (open) => set({ analyticsPanelOpen: open }),

  // Modals
  alertConfigOpen: false,
  setAlertConfigOpen: (open) => set({ alertConfigOpen: open }),
  reportDownloadOpen: false,
  setReportDownloadOpen: (open) => set({ reportDownloadOpen: open }),
  alertPanelOpen: false,
  setAlertPanelOpen: (open) => set({ alertPanelOpen: open }),

  // Alert config
  alertConfig: {
    sensitivity: 50,
    email: '',
    webhookUrl: '',
  },
  setAlertConfig: (config) =>
    set((state) => ({ alertConfig: { ...state.alertConfig, ...config } })),

  // Time slider
  isPlaying: false,
  setIsPlaying: (playing) => set({ isPlaying: playing }),

  // Map click data
  clickedPoint: null,
  setClickedPoint: (point) => set({ clickedPoint: point }),
}))
