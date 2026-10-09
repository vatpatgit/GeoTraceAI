import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/store/useAppStore'

const m = vi.hoisted(() => ({ search: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, sentinel: { search: m.search } } }
})
import QuickComparePanel from './QuickComparePanel'

const scene = (id: string, d: string) => ({ product_id: id, collection: 'c', provider: 'cdse', acquired_at: d, cloud_cover_pct: 2, footprint: null, coverage_of_aoi_pct: 100, thumbnail_url: null, resolution_m: 10, platform: 'S2', processing_level: 'L2A', properties: {} })

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ quickCompare: null, drawMode: false, drawnBox: null, regions: [], system: { sentinel: [{ provider: 'cdse', configured: true, catalog: 'available', imagery: 'available', detail: '' }] } as never })
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }))
})

async function fill(w: string, s: string, e: string, n: string) {
  await userEvent.type(screen.getByLabelText('West (lon)'), w)
  await userEvent.type(screen.getByLabelText('South (lat)'), s)
  await userEvent.type(screen.getByLabelText('East (lon)'), e)
  await userEvent.type(screen.getByLabelText('North (lat)'), n)
}

describe('QuickComparePanel', () => {
  it('rejects a box that is too large or mis-ordered and does not call the API', async () => {
    render(<QuickComparePanel />)
    await fill('10', '10', '12', '12')
    expect(screen.getByRole('alert')).toHaveTextContent(/at most 0.5/)
    expect(screen.getByRole('button', { name: 'Retrieve images and compare' })).toBeDisabled()
    expect(m.search).not.toHaveBeenCalled()
  })

  it('searches the typed box with a window around each date and reports a missing scene honestly', async () => {
    m.search.mockResolvedValue({ before: [], after: [scene('a', '2026-08-09T10:00:00Z')], suggested_before: null, suggested_after: 'a' })
    render(<QuickComparePanel />)
    await fill('-62.3', '-10.9', '-62.27', '-10.87')
    await userEvent.click(screen.getByRole('button', { name: 'Retrieve images and compare' }))
    await waitFor(() => expect(m.search).toHaveBeenCalledWith(expect.objectContaining({ bbox: [-62.3, -10.9, -62.27, -10.87] })))
    expect(await screen.findByText(/No Sentinel-2 scene with at most 10% cloud within/)).toBeInTheDocument()
    expect(useAppStore.getState().quickCompare).toBeNull()
    // every search asks for clear images only, and widens the window around the dates before giving up
    const calls = m.search.mock.calls.map((c) => c[0])
    expect(calls.every((c) => c.max_cloud_cover_pct === 10)).toBe(true)
    const span = (c: { before: { start: string; end: string } }) => Date.parse(c.before.end) - Date.parse(c.before.start)
    expect(calls.length).toBeGreaterThan(1)
    expect(span(calls[calls.length - 1])).toBeGreaterThan(span(calls[0]))
  })

  it('fills the W/S/E/N fields from a rectangle drawn on the map', async () => {
    render(<QuickComparePanel />)
    act(() => useAppStore.getState().setDrawnBox([72.87365, 19.06321, 73.01014, 19.15533]))
    for (const [label, v] of [['West (lon)', '72.87365'], ['South (lat)', '19.06321'], ['East (lon)', '73.01014'], ['North (lat)', '19.15533']])
      await waitFor(() => expect(screen.getByLabelText(label)).toHaveValue(v))
    expect(screen.getByText(/Rectangle ≈/)).toBeInTheDocument()
  })
})
