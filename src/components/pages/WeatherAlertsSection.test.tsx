import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Aoi, WeatherAlert } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
const m = vi.hoisted(() => ({ list: vi.fn(), events: vi.fn(), refresh: vi.fn(), setMonitoring: vi.fn(), markRead: vi.fn(), aois: vi.fn(), createAoi: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, weather: { list: m.list, events: m.events, refresh: m.refresh, setMonitoring: m.setMonitoring, markRead: m.markRead }, projects: { ...actual.api.projects, aois: m.aois, createAoi: m.createAoi } } }
})
import WeatherAlertsSection from './WeatherAlertsSection'

const aoi = { id: 'aoi1', name: 'Elbe valley', area_km2: 1500 } as unknown as Aoi
const poly = { type: 'Polygon' as const, coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] }
const alert = (over: Partial<WeatherAlert> = {}): WeatherAlert => ({
  id: 'w1', aoi_id: 'aoi1', aoi_name: 'Elbe valley', provider: 'openweather', source_alert_id: 'S1', source: 'government', title: 'Flood warning', description: 'River levels rising',
  tags: ['flood'], severity: 'severe', urgency: 'expected', certainty: 'likely', industry: [], geometry: poly, start_time: '2026-10-10T12:00:00Z', end_time: '2026-10-10T15:00:00Z',
  status: 'active', change_count: 0, first_seen_at: '2026-10-10T12:00:00Z', last_seen_at: '2026-10-10T12:00:00Z', last_checked_at: '2026-10-10T12:00:00Z', notified_at: null, ...over,
})
const state = (over = {}) => ({ aoi_id: 'aoi1', aoi_name: 'Elbe valley', last_checked_at: '2026-10-10T12:00:00Z', last_status: 'ok', last_error: null, alert_count: 1, monitoring: false, ...over })

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ authUser: { id: 'u', email: 'u@x.test', name: 'U', role: 'user' }, activeProjectId: 'p1', projects: [{ id: 'p1' } as never], regions: [], weatherAlerts: [], selectedWeatherId: null, flyRequest: null, toasts: [] })
  m.aois.mockResolvedValue([aoi])
  m.events.mockResolvedValue([])
  m.list.mockResolvedValue({ configured: true, items: [], aois: [] })
})

describe('WeatherAlertsSection', () => {
  it('shows alerts with severity word, tags, source, certainty, urgency, time and last-retrieved info', async () => {
    m.list.mockResolvedValue({ configured: true, items: [alert()], aois: [state()] })
    render(<WeatherAlertsSection />)
    expect(await screen.findByText('Flood warning')).toBeInTheDocument()
    expect(screen.getByLabelText('Severity: severe')).toHaveTextContent('severe')
    expect(screen.getByText('flood')).toBeInTheDocument()
    expect(screen.getByText('River levels rising')).toBeInTheDocument()
    expect(screen.getByText(/government · OpenWeather/)).toBeInTheDocument()
    expect(screen.getByText('likely')).toBeInTheDocument()
    expect(screen.getByText(/Last retrieved/)).toBeInTheDocument()
    expect(screen.getByText(/not the extent of damage/)).toBeInTheDocument()
  })

  it('shares the stored alerts with the map through the store', async () => {
    m.list.mockResolvedValue({ configured: true, items: [alert()], aois: [state()] })
    render(<WeatherAlertsSection />)
    await screen.findByText('Flood warning')
    expect(useAppStore.getState().weatherAlerts.map((a) => a.id)).toEqual(['w1'])
  })

  it('"Map" selects the alert, requests a fit to its geometry and opens the map', async () => {
    m.list.mockResolvedValue({ configured: true, items: [alert()], aois: [state()] })
    render(<WeatherAlertsSection />)
    await userEvent.click(await screen.findByRole('button', { name: /Show Flood warning on the map/ }))
    const s = useAppStore.getState()
    expect(s.selectedWeatherId).toBe('w1')
    expect(s.flyRequest?.bbox).toEqual([10, 50, 11, 51])
    expect(push).toHaveBeenCalledWith('/map')
  })

  it('an alert without geometry cannot be shown on the map and says why', async () => {
    m.list.mockResolvedValue({ configured: true, items: [alert({ geometry: null })], aois: [state()] })
    render(<WeatherAlertsSection />)
    const btn = await screen.findByRole('button', { name: /Show Flood warning on the map/ })
    expect(btn).toBeDisabled()
    expect(screen.getByText('no geometry supplied')).toBeInTheDocument()
  })

  it('an empty provider answer is presented as a valid result, not an error', async () => {
    m.list.mockResolvedValue({ configured: true, items: [], aois: [state({ alert_count: 0 })] })
    render(<WeatherAlertsSection />)
    expect(await screen.findByText('No active weather alerts for this area')).toBeInTheDocument()
    expect(screen.getByText(/valid answer, not an error/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('refresh calls the backend for the selected AOI and reports new/updated/unchanged counts', async () => {
    m.refresh.mockResolvedValue({ aoi_id: 'aoi1', checked_at: '', cached: false, new: 1, updated: 0, unchanged: 2, expired: 0, total_active: 3, items: [] })
    render(<WeatherAlertsSection />)
    await userEvent.click(await screen.findByRole('button', { name: /Get alerts/ }))
    await waitFor(() => expect(m.refresh).toHaveBeenCalledWith({ aoi_id: 'aoi1', force: false }))
    expect(await screen.findByText(/1 new · 0 updated · 2 unchanged/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Force refresh/ }))
    await waitFor(() => expect(m.refresh).toHaveBeenLastCalledWith({ aoi_id: 'aoi1', force: true }))
  })

  it('provider errors are shown with a retry, never as an empty list', async () => {
    const { ApiError } = await import('@/lib/api')
    m.refresh.mockRejectedValue(new ApiError(502, 'OpenWeather rejected the API key, or the key plan does not include the Alerts product (HTTP 401).', 'provider_auth_failed'))
    render(<WeatherAlertsSection />)
    await userEvent.click(await screen.findByRole('button', { name: /Get alerts/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/does not include the Alerts product/)
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('when the server has no key, refresh is disabled and the reason is stated', async () => {
    m.list.mockResolvedValue({ configured: false, items: [], aois: [] })
    render(<WeatherAlertsSection />)
    expect(await screen.findByText(/OPENWEATHER_API_KEY/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Get alerts/ })).toBeDisabled()
  })

  it('viewers can read stored alerts but get no refresh controls', async () => {
    useAppStore.setState({ authUser: { id: 'v', email: 'v@x.test', name: 'V', role: 'viewer' } })
    m.list.mockResolvedValue({ configured: true, items: [alert()], aois: [state()] })
    render(<WeatherAlertsSection />)
    await screen.findByText('Flood warning')
    expect(screen.queryByRole('button', { name: /Get alerts/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  it('new/updated alerts are announced and can be marked read', async () => {
    m.events.mockResolvedValue([{ id: 'e1', alert_id: 'w1', aoi_id: 'aoi1', kind: 'new', changes: [], title: 'Flood warning', severity: 'severe', created_at: '', read_at: null }])
    m.list.mockResolvedValue({ configured: true, items: [alert()], aois: [state()] })
    m.markRead.mockResolvedValue({ marked_read: 1 })
    render(<WeatherAlertsSection />)
    expect(await screen.findByText(/New: Flood warning/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mark read' }))
    await waitFor(() => expect(m.markRead).toHaveBeenCalledWith({ all: true }))
    await waitFor(() => expect(screen.queryByText(/since you last looked/)).not.toBeInTheDocument())
  })

  it('monitoring can be switched on for the AOI', async () => {
    m.setMonitoring.mockResolvedValue(state({ monitoring: true }))
    m.list.mockResolvedValue({ configured: true, items: [], aois: [state({ monitoring: false })] })
    render(<WeatherAlertsSection />)
    await userEvent.click(await screen.findByRole('switch', { name: 'Monitor this AOI for weather alerts' }))
    await waitFor(() => expect(m.setMonitoring).toHaveBeenCalledWith('aoi1', true))
  })
})
