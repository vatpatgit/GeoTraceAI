import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { HazardAlert } from '@/lib/api/hazards'
import { useAppStore } from '@/store/useAppStore'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
const m = vi.hoisted(() => ({ list: vi.fn(), refresh: vi.fn(), markRead: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, hazards: { list: m.list, refresh: m.refresh, markRead: m.markRead, status: vi.fn() } } }
})
import HazardAlertsSection from './HazardAlertsSection'
import HazardWatcher from '../shell/HazardWatcher'

const alert = (over: Partial<HazardAlert> = {}): HazardAlert => ({
  id: 'h1', aoi_id: 'a1', aoi_name: 'Panama test', kind: 'earthquake', title: 'M5.8 earthquake, 1 km S of El Cacao, Panama', severity: 'medium', lat: 7.6, lon: -80.9,
  distance_km: 18.5, occurred_at: '2026-10-09T11:00:00Z', details: { magnitude: 5.8, depth_km: 10, tsunami_flag: false, url: 'https://earthquake.usgs.gov/e/1' },
  status: 'active', first_seen_at: '2026-10-09T11:05:00Z', last_seen_at: '2026-10-09T11:05:00Z', read_at: null, ...over,
})
const refreshed = { aois: 1, new: 1, updated: 0, expired: 0, active: 1, cached: false, fetched: { earthquake: 51, fire: 2017, storm: 49 }, errors: {}, checked_at: '2026-10-09T12:00:00Z' }

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ toasts: [], flyRequest: null })
  m.list.mockResolvedValue([alert()])
  m.refresh.mockResolvedValue(refreshed)
  m.markRead.mockResolvedValue({ marked_read: 1 })
})

describe('HazardAlertsSection', () => {
  it('shows real alert facts with severity as a word, distance, source link and the not-a-detection disclaimer', async () => {
    render(<HazardAlertsSection />)
    expect(await screen.findByText(/M5.8 earthquake/)).toBeInTheDocument()
    expect(screen.getByText('medium')).toBeInTheDocument()
    expect(screen.getByText(/19 km from the area|18 km from the area/)).toBeInTheDocument()
    expect(screen.getByText('5.8')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'USGS event page' })).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText(/separate from\s+satellite change detections/)).toBeInTheDocument()
  })

  it('checks the feed on demand, reports unreadable feeds as unknown, and flies to the event', async () => {
    m.refresh.mockResolvedValue({ ...refreshed, errors: { fire: 'The hazard feed returned unreadable data.' } })
    render(<HazardAlertsSection />)
    await screen.findByText(/M5.8 earthquake/)
    await userEvent.click(screen.getByRole('button', { name: /Check now/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/unknown \(not “no alerts”\)/)
    expect(m.refresh).toHaveBeenCalledWith({ force: true })
    await userEvent.click(screen.getByRole('button', { name: /Show M5.8 earthquake/ }))
    expect(push).toHaveBeenCalledWith('/map')
    expect(useAppStore.getState().flyRequest?.center).toEqual([-80.9, 7.6])
  })

  it('marks everything read and shows an honest empty state with what was reviewed', async () => {
    render(<HazardAlertsSection />)
    await userEvent.click(await screen.findByRole('button', { name: /Mark 1 read/ }))
    expect(m.markRead).toHaveBeenCalledWith({ all: true })
    m.list.mockResolvedValue([])
    await userEvent.click(screen.getByRole('button', { name: /Check now/ }))
    expect(await screen.findByText('No active hazard alerts near your areas')).toBeInTheDocument()
    expect(screen.getByText(/2017 fire records/)).toBeInTheDocument()
  })

  it('surfaces a load error instead of an empty list', async () => {
    m.list.mockRejectedValue(new Error('x'))
    render(<HazardAlertsSection />)
    expect(await screen.findByText(/Could not load hazard alerts/)).toBeInTheDocument()
  })
})

describe('HazardWatcher', () => {
  it('announces new unread alerts once, using one summary toast', async () => {
    m.list.mockResolvedValue([alert(), alert({ id: 'h2', severity: 'high', title: 'M6.1 earthquake' })])
    render(<HazardWatcher />)
    await waitFor(() => expect(useAppStore.getState().toasts.length).toBe(1))
    const t = useAppStore.getState().toasts[0]
    expect(t.kind).toBe('error') // the highest severity decides the tone
    expect(t.text).toMatch(/M6.1 earthquake \(\+1 more\)/)
  })

  it('stays silent when the feed or network fails (the page shows the real error on demand)', async () => {
    m.refresh.mockRejectedValue(new Error('offline'))
    render(<HazardWatcher />)
    await act(async () => { await Promise.resolve() })
    expect(useAppStore.getState().toasts).toHaveLength(0)
  })
})
