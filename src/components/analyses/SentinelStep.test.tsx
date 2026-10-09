import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/store/useAppStore'

const m = vi.hoisted(() => ({ search: vi.fn(), acquire: vi.fn(), get: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('./AoiPickerMap', () => ({ default: () => <div /> }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, sentinel: { search: m.search, acquire: m.acquire }, analyses: { ...actual.api.analyses, get: m.get } } }
})

import SentinelStep from './SentinelStep'

const scene = (id: string, d: string) => ({ product_id: id, collection: 'c', provider: 'cdse', acquired_at: d, cloud_cover_pct: 3, footprint: null, coverage_of_aoi_pct: 100, thumbnail_url: null, resolution_m: 10, platform: 'S2', processing_level: 'L2A', properties: {} })

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ system: { sentinel: [{ provider: 'cdse', configured: true, catalog: 'available', imagery: 'available', detail: '' }], limits: { max_aoi_km2: 2500 }, ml: { any_model_ready: false } } as never })
})

describe('SentinelStep for a monitored region', () => {
  it('searches the region bbox with two date windows and acquires the chosen scenes', async () => {
    m.search.mockResolvedValue({ provider: 'cdse', aoi_geometry: { type: 'Polygon', coordinates: [[[1, 2], [3, 2], [3, 4], [1, 4], [1, 2]]] }, aoi_area_km2: 10, before: [scene('b1', '2023-06-01T10:00:00Z')], after: [scene('a1', '2024-06-01T10:00:00Z')], suggested_before: 'b1', suggested_after: 'a1', suggestion_rule: 'least cloud', warnings: [] })
    m.acquire.mockResolvedValue({ analysis_id: 'an1', status: 'queued', before_product_id: 'b1', after_product_id: 'a1', message: '' })
    m.get.mockResolvedValue({ id: 'an1', name: 'x', status: 'queued', bounds: null })
    render(<SentinelStep projectId="p1" region={{ name: 'Reserve', bbox: [1, 2, 3, 4], area_km2: 10 }} />)
    expect(screen.getByText('Reserve')).toBeInTheDocument()
    expect(screen.queryByLabelText('Longitude')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Search Sentinel-2 scenes/ }))
    await waitFor(() => expect(m.search).toHaveBeenCalledWith(expect.objectContaining({ bbox: [1, 2, 3, 4], project_id: 'p1', before: expect.any(Object), after: expect.any(Object) })))
    await userEvent.click(await screen.findByRole('button', { name: /Retrieve selected scenes and run/ }))
    await waitFor(() => expect(m.acquire).toHaveBeenCalledWith(expect.objectContaining({ project_id: 'p1', before_product_id: 'b1', after_product_id: 'a1' })))
    expect(useAppStore.getState().viewMode).toBe('compare')
  })
})
