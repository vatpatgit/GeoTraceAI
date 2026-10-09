import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Analysis, Incident } from '@/lib/api'
import { EMPTY_FILTERS, useAppStore } from '@/store/useAppStore'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }), usePathname: () => '/' }))

const m = vi.hoisted(() => ({
  incidents: vi.fn(), stats: vi.fn(), rules: vi.fn(), setStatus: vi.fn(), createRule: vi.fn(),
  weatherList: vi.fn(), weatherEvents: vi.fn(), aois: vi.fn(),
  download: vi.fn(), exportFn: vi.fn(), features: vi.fn(), review: vi.fn(), overview: vi.fn(), regionsList: vi.fn(), query: vi.fn(),
}))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return {
    ...actual,
    apiFetch: vi.fn().mockResolvedValue(undefined),
    api: {
      ...actual.api,
      alerts: { incidents: m.incidents, stats: m.stats, rules: m.rules, setStatus: m.setStatus, createRule: m.createRule, updateRule: vi.fn(), deleteRule: vi.fn() },
      reports: { download: m.download },
      analyses: { ...actual.api.analyses, export: m.exportFn, features: m.features, review: m.review },
      analytics: { overview: m.overview, query: m.query },
      regions: { list: m.regionsList },
      weather: { list: m.weatherList, events: m.weatherEvents, refresh: vi.fn(), setMonitoring: vi.fn(), markRead: vi.fn(), status: vi.fn() },
      projects: { ...actual.api.projects, aois: m.aois },
    },
  }
})

import AlertsPage from './AlertsPage'
import AnalyticsPage from './AnalyticsPage'
import ChangesPage from './ChangesPage'
import RegionsPage from './RegionsPage'
import ReportsPage from './ReportsPage'

const incident = (over: Partial<Incident> = {}): Incident => ({
  id: 'i1', rule_id: 'r1', rule_name: 'Reserve watch', analysis_id: 'a1', analysis_name: 'Run A', feature_id: 'f1', severity: 'high', category: 'vegetation_decrease', status: 'open',
  title: 'HIGH: vegetation decrease inside Reserve', message: 'A 3 ha detection intersects the reserve.', evidence: { rule: { min_area_m2: 1 }, matched: { scope: [{ name: 'Reserve' }] }, analysis: {} },
  area_m2: 30000, confidence: null, centroid: [-62, -10], bbox: [-62.1, -10.1, -61.9, -9.9], region_id: null, detected_at: '2026-10-01T00:00:00Z', created_at: '2026-10-01T00:00:00Z',
  acknowledged_at: null, resolved_at: null, resolution_note: null, is_demo: false, ...over,
})
const analysis = (over: Partial<Analysis> = {}): Analysis => ({
  id: 'a1', project_id: 'p1', name: 'Run A', status: 'completed', is_demo: false, method: 'spectral_cva', before_date: '2024-01-01T00:00:00Z', after_date: '2024-06-01T00:00:00Z', model_id: null,
  summary: { feature_count: 3, total_changed_area_m2: 50000, by_category: { vegetation_decrease: 3 }, by_severity: { high: 3 }, area_by_category_m2: { vegetation_decrease: 50000 } },
  ...over,
} as unknown as Analysis)

function asUser(role: 'admin' | 'user' | 'viewer') {
  useAppStore.setState({ authUser: { id: 'u', email: 'u@x.test', name: 'U', role }, authStatus: 'authenticated' })
}

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ analyses: [], activeAnalysisId: null, regions: [], filters: EMPTY_FILTERS, toasts: [] })
  asUser('user')
  m.stats.mockResolvedValue({ by_status: { open: 1, acknowledged: 0, resolved: 0 }, unresolved_by_severity: { high: 1 }, unresolved: 1 })
  m.rules.mockResolvedValue([])
  m.weatherList.mockResolvedValue({ configured: true, items: [], aois: [] })
  m.weatherEvents.mockResolvedValue([])
  m.aois.mockResolvedValue([])
})

describe('AlertsPage', () => {
  it('shows incidents with their evidence and acknowledges one through the API', async () => {
    m.incidents.mockResolvedValue({ total: 1, open: 1, limit: 25, offset: 0, items: [incident()] })
    m.setStatus.mockResolvedValue(incident({ status: 'acknowledged' }))
    render(<AlertsPage />)
    expect(await screen.findByText('HIGH: vegetation decrease inside Reserve')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show evidence' }))
    expect(screen.getByText(/Why this alert fired/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
    await waitFor(() => expect(m.setStatus).toHaveBeenCalledWith('i1', 'acknowledged', undefined))
  })

  it('"Map" selects the detection and navigates', async () => {
    m.incidents.mockResolvedValue({ total: 1, open: 1, limit: 25, offset: 0, items: [incident()] })
    render(<AlertsPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Show HIGH: vegetation decrease inside Reserve on the map/ }))
    expect(useAppStore.getState().selectedFeatureId).toBe('f1')
    expect(useAppStore.getState().activeAnalysisId).toBe('a1')
    expect(push).toHaveBeenCalledWith('/map')
  })

  it('empty state explains that rules are needed', async () => {
    m.incidents.mockResolvedValue({ total: 0, open: 0, limit: 25, offset: 0, items: [] })
    render(<AlertsPage />)
    expect(await screen.findByText('No incidents match')).toBeInTheDocument()
    expect(screen.getByText(/Create a rule below/)).toBeInTheDocument()
  })

  it('an API failure is shown as an error, not as an empty list', async () => {
    const { ApiError } = await import('@/lib/api')
    m.incidents.mockRejectedValue(new ApiError(0, 'Cannot reach the GeoTrace backend.', 'network'))
    render(<AlertsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the GeoTrace backend.')
    expect(screen.queryByText('No incidents match')).not.toBeInTheDocument()
  })

  it('viewers get no mutation controls', async () => {
    asUser('viewer')
    m.incidents.mockResolvedValue({ total: 1, open: 1, limit: 25, offset: 0, items: [incident()] })
    render(<AlertsPage />)
    await screen.findByText('HIGH: vegetation decrease inside Reserve')
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /New rule/ })).not.toBeInTheDocument()
  })

  it('rule editor validates distance rules before saving', async () => {
    useAppStore.setState({ regions: [{ id: 'g1', name: 'Reserve', description: null, geometry: null, center_lat: 0, center_lng: 0, area_km2: 1, risk_level: 'high', created_at: '' }] })
    m.incidents.mockResolvedValue({ total: 0, open: 0, limit: 25, offset: 0, items: [] })
    m.createRule.mockResolvedValue({})
    render(<AlertsPage />)
    await userEvent.click(await screen.findByRole('button', { name: /New rule/ }))
    const save = screen.getByRole('button', { name: 'Create rule' })
    expect(save).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Name'), 'Near reserve')
    await userEvent.selectOptions(screen.getByLabelText('Scope: monitored region'), 'g1')
    await userEvent.selectOptions(screen.getByLabelText('Relation to region'), 'within_distance')
    expect(save).toBeDisabled()
    expect(screen.getByText('Enter a distance in metres.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Distance (m)'), '500')
    expect(save).toBeEnabled()
    await userEvent.click(save)
    await waitFor(() => expect(m.createRule).toHaveBeenCalledWith(expect.objectContaining({ name: 'Near reserve', region_id: 'g1', region_relation: 'within_distance', distance_m: 500 })))
  })
})

describe('ReportsPage', () => {
  it('lists only completed analyses and downloads the requested format', async () => {
    useAppStore.setState({ analyses: [analysis(), analysis({ id: 'a2', name: 'Running', status: 'detecting_changes' })] })
    m.download.mockResolvedValue({ filename: 'r.pdf', featureCount: null })
    render(<ReportsPage />)
    expect(screen.getByText('Run A')).toBeInTheDocument()
    expect(screen.queryByText('Running')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /PDF/ }))
    await waitFor(() => expect(m.download).toHaveBeenCalledWith('a1', 'pdf'))
    await userEvent.click(screen.getByRole('button', { name: /GeoPackage/ }))
    await waitFor(() => expect(m.exportFn).toHaveBeenCalledWith('a1', 'gpkg'))
  })
  it('marks demo analyses and shows an empty state otherwise', () => {
    useAppStore.setState({ analyses: [analysis({ is_demo: true })] })
    const { unmount } = render(<ReportsPage />)
    expect(screen.getByText(/demo data/i)).toBeInTheDocument()
    unmount()
    useAppStore.setState({ analyses: [] })
    render(<ReportsPage />)
    expect(screen.getByText('No completed analyses to report on')).toBeInTheDocument()
  })
})

describe('ChangesPage', () => {
  const feature = { id: 'f1', seq: 7, category: 'vegetation_decrease', category_basis: 'spectral_index', area_m2: 12000, magnitude: 0.61, confidence: null, severity: 'high', review_status: 'unreviewed', bbox: [0, 0, 1, 1] }
  it('filters server-side and reviews a detection', async () => {
    useAppStore.setState({ analyses: [analysis()] })
    m.features.mockResolvedValue({ total: 1, limit: 30, offset: 0, items: [feature] })
    m.review.mockResolvedValue({})
    render(<ChangesPage />)
    expect(await screen.findByText('Vegetation decrease')).toBeInTheDocument()
    expect(screen.getByText('n/a')).toBeInTheDocument() // baseline detectors have no score
    await userEvent.click(screen.getByRole('button', { name: 'critical' }))
    await waitFor(() => expect(m.features).toHaveBeenLastCalledWith('a1', expect.objectContaining({ severity: ['critical'] }), expect.anything()))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm detection 7' }))
    await waitFor(() => expect(m.review).toHaveBeenCalledWith('a1', 'f1', 'confirmed'))
  })
  it('empty filter result is explained', async () => {
    useAppStore.setState({ analyses: [analysis()] })
    m.features.mockResolvedValue({ total: 0, limit: 30, offset: 0, items: [] })
    render(<ChangesPage />)
    expect(await screen.findByText('No detections match these filters')).toBeInTheDocument()
  })
})

describe('RegionsPage', () => {
  it('only administrators can add regions, and invalid bounds are rejected client-side', async () => {
    asUser('user')
    const { unmount } = render(<RegionsPage />)
    expect(screen.queryByText('Add a region (bounding box)')).not.toBeInTheDocument()
    unmount()
    asUser('admin')
    render(<RegionsPage />)
    await userEvent.type(screen.getByLabelText('Name'), 'Park')
    const w = screen.getByLabelText(/^west/); const s = screen.getByLabelText(/^south/); const e = screen.getByLabelText(/^east/); const n = screen.getByLabelText(/^north/)
    await userEvent.type(w, '10'); await userEvent.type(s, '5'); await userEvent.type(e, '9'); await userEvent.type(n, '6')
    expect(screen.getByRole('button', { name: /Create region/ })).toBeDisabled()
    expect(screen.getByText(/West must be less than east/)).toBeInTheDocument()
    await userEvent.clear(e); await userEvent.type(e, '11')
    expect(screen.getByRole('button', { name: /Create region/ })).toBeEnabled()
  })
})

describe('AnalyticsPage', () => {
  it('answers a question via the API and shows an honest message for unsupported ones', async () => {
    useAppStore.setState({ analyses: [analysis()] })
    m.overview.mockResolvedValue({ series: [] })
    m.query.mockResolvedValueOnce({ question: 'x', interpreted_as: {}, operation: 'none', understood: false, data: {}, answer: 'I can only answer questions that map to the supported analyses.', answer_source: 'deterministic', measured_facts: [], caveats: [], references: [], suggestions: ['Which are the 5 largest changes?'] })
    render(<AnalyticsPage />)
    await userEvent.type(screen.getByLabelText('Ask a question'), 'Will it rain tomorrow?')
    await userEvent.click(screen.getByRole('button', { name: /^Ask$/ }))
    expect(await screen.findByText(/I can only answer questions/)).toBeInTheDocument()
    expect(m.query).toHaveBeenCalledWith(expect.objectContaining({ question: 'Will it rain tomorrow?', analysis_id: 'a1' }))
    expect(await screen.findByText(/Not enough history for a trend/)).toBeInTheDocument()
    expect(within(screen.getByText(/Not enough history/).closest('section')!).getByText(/does not extrapolate/)).toBeInTheDocument()
  })
})
