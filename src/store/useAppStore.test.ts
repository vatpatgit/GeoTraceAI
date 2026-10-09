import { beforeEach, describe, expect, it } from 'vitest'
import type { Analysis } from '@/lib/api'
import { EMPTY_FILTERS, hasActiveFilters, selectActiveAnalysis, toFeatureFilters, useAppStore } from './useAppStore'

const analysis = (id: string, bounds: [number, number, number, number] | null = [1, 2, 3, 4]): Analysis => ({ id, name: id, status: 'completed', bounds } as unknown as Analysis)

beforeEach(() => {
  useAppStore.setState({ analyses: [], activeAnalysisId: null, selectedFeatureId: null, filters: EMPTY_FILTERS, featuresVersion: 0, flyRequest: null, layerState: useAppStore.getState().layerState })
})

describe('shared selection', () => {
  it('selecting a feature opens the right panel and requests a fly-to', () => {
    useAppStore.setState({ rightPanelOpen: false })
    useAppStore.getState().selectFeature('f1', { fly: true, center: [10, 20] })
    const s = useAppStore.getState()
    expect(s.selectedFeatureId).toBe('f1')
    expect(s.rightPanelOpen).toBe(true)
    expect(s.flyRequest).toMatchObject({ center: [10, 20], zoom: 15 })
  })
  it('deselecting does not move the camera', () => {
    useAppStore.getState().selectFeature('f1')
    const before = useAppStore.getState().flyRequest
    useAppStore.getState().selectFeature(null, { fly: true })
    expect(useAppStore.getState().selectedFeatureId).toBeNull()
    expect(useAppStore.getState().flyRequest).toBe(before)
  })
  it('each fly request gets a new id so repeated requests are honoured', () => {
    useAppStore.getState().requestFly({ center: [0, 0] })
    const a = useAppStore.getState().flyRequest!.id
    useAppStore.getState().requestFly({ center: [0, 0] })
    expect(useAppStore.getState().flyRequest!.id).toBeGreaterThan(a)
  })
})

describe('active analysis', () => {
  it('switching analysis clears selection and filters, bumps the data version and flies to the bounds', () => {
    useAppStore.setState({ analyses: [analysis('a'), analysis('b')], selectedFeatureId: 'f', filters: { ...EMPTY_FILTERS, severities: ['high'] } })
    useAppStore.getState().setActiveAnalysis('b')
    const s = useAppStore.getState()
    expect(selectActiveAnalysis(s)?.id).toBe('b')
    expect(s.selectedFeatureId).toBeNull()
    expect(s.filters).toEqual(EMPTY_FILTERS)
    expect(s.featuresVersion).toBe(1)
    expect(s.flyRequest?.bbox).toEqual([1, 2, 3, 4])
  })
  it('upsert replaces by id and prepends new analyses', () => {
    useAppStore.setState({ analyses: [analysis('a')] })
    useAppStore.getState().upsertAnalysis({ ...analysis('a'), name: 'renamed' })
    useAppStore.getState().upsertAnalysis(analysis('c'))
    expect(useAppStore.getState().analyses.map((a) => `${a.id}:${a.name}`)).toEqual(['c:c', 'a:renamed'])
  })
})

describe('filters', () => {
  it('translate to server-side filters and flag activity', () => {
    const f = { ...EMPTY_FILTERS, severities: ['high' as const, 'critical' as const], minAreaM2: 500 }
    expect(toFeatureFilters(f)).toMatchObject({ severity: ['high', 'critical'], min_area_m2: 500 })
    expect(toFeatureFilters(EMPTY_FILTERS)).toEqual({ severity: undefined, category: undefined, review_status: undefined, min_area_m2: undefined })
    expect(hasActiveFilters(f)).toBe(true)
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false)
  })
  it('changing filters bumps the version so list, map and globe refetch together', () => {
    useAppStore.getState().setFilters({ severities: ['low'] })
    expect(useAppStore.getState().featuresVersion).toBe(1)
    useAppStore.getState().resetFilters()
    expect(useAppStore.getState().filters).toEqual(EMPTY_FILTERS)
    expect(useAppStore.getState().featuresVersion).toBe(2)
  })
})

describe('layer state', () => {
  it('toggles visibility and clamps opacity', () => {
    const st = useAppStore.getState()
    st.setLayerVisible('change-score', true)
    st.setLayerOpacity('change-score', 4)
    expect(useAppStore.getState().layerState['change-score']).toMatchObject({ visible: true, opacity: 1 })
    st.setLayerOpacity('change-score', -1)
    expect(useAppStore.getState().layerState['change-score'].opacity).toBe(0)
  })
  it('clamps compare position', () => {
    useAppStore.getState().setComparePosition(3)
    expect(useAppStore.getState().comparePosition).toBe(1)
  })
})

describe('sign out', () => {
  it('drops user-scoped state', () => {
    useAppStore.setState({ analyses: [analysis('a')], activeAnalysisId: 'a' })
    useAppStore.getState().signOut()
    const s = useAppStore.getState()
    expect(s.analyses).toEqual([])
    expect(s.activeAnalysisId).toBeNull()
    expect(s.authStatus).toBe('unauthenticated')
  })
})
