import { render, screen, waitFor } from '@testing-library/react'
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
  useAppStore.setState({ quickCompare: null, regions: [], system: { sentinel: [{ provider: 'cdse', configured: true, catalog: 'available', imagery: 'available', detail: '' }] } as never })
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
    expect(await screen.findByText(/No Sentinel-2 scene within/)).toBeInTheDocument()
    expect(useAppStore.getState().quickCompare).toBeNull()
  })
})
