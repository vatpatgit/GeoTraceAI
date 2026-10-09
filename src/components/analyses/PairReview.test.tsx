import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ImageryAsset, PairValidation } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
const m = vi.hoisted(() => ({ validatePair: vi.fn(), renderPng: vi.fn(), create: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, imagery: { ...actual.api.imagery, validatePair: m.validatePair, renderPng: m.renderPng }, analyses: { ...actual.api.analyses, create: m.create } } }
})
import PairReview from './PairReview'

const asset = (id: string, name: string, date: string | null): ImageryAsset => ({ id, original_filename: name, acquisition_start: date, band_count: 4, pixel_size_m: 10 } as unknown as ImageryAsset)
const validation = (over: Partial<PairValidation> = {}): PairValidation => ({
  ok: true, issues: [], analysis_crs_epsg: 32633, overlap: { fraction_of_before: 1, bounds_wgs84: [15.0, 40.6, 15.05, 40.64] }, resolution: {},
  bands: { common_roles: ['red', 'green', 'blue', 'nir'], needs_confirmation: false, notes: [] }, suggested_pixel_size_m: 10, model_available: true, suggested_method: 'spectral_cva', suggested_method_reason: '', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }))
  useAppStore.setState({ quickCompare: null, system: null, flyRequest: null, viewMode: 'map', toasts: [] })
})

describe('PairReview: automatic comparison after upload', () => {
  it('opens the slider comparison by itself once the pair validates (no button press, no dates needed)', async () => {
    m.validatePair.mockResolvedValue(validation())
    m.renderPng.mockResolvedValueOnce('blob:before').mockResolvedValueOnce('blob:after')
    render(<PairReview projectId="p1" before={asset('b1', 'before.tif', null)} after={asset('a1', 'after.tif', null)} inputType="upload" autoCompare />)
    await waitFor(() => expect(push).toHaveBeenCalledWith('/map'))
    expect(useAppStore.getState().viewMode).toBe('compare')
    expect(useAppStore.getState().quickCompare?.source).toMatchObject({ kind: 'upload', beforeAssetId: 'b1', afterAssetId: 'a1' })
    expect(m.renderPng).toHaveBeenCalledTimes(2)  // exactly once per image, even across re-renders
  })

  it('does not open anything for an invalid pair and shows a visible error with retry when rendering fails', async () => {
    const { ApiError } = await import('@/lib/api')
    m.validatePair.mockResolvedValue(validation({ ok: false, issues: [{ level: 'error', code: 'no_overlap', message: 'The rasters do not overlap.', details: {} }] }))
    const { unmount } = render(<PairReview projectId="p1" before={asset('b1', 'a.tif', null)} after={asset('a1', 'b.tif', null)} inputType="upload" autoCompare />)
    await screen.findByText('Pair cannot be processed')
    expect(m.renderPng).not.toHaveBeenCalled()
    unmount()
    m.validatePair.mockResolvedValue(validation())
    m.renderPng.mockRejectedValue(new ApiError(500, 'Rendering failed (500).'))
    render(<PairReview projectId="p1" before={asset('b3', 'a.tif', null)} after={asset('a3', 'b.tif', null)} inputType="upload" autoCompare />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not open the comparison: Rendering failed/)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('PairReview: compare two uploaded GeoTIFFs', () => {
  it('renders both images over their common area and opens the compare view with an upload source', async () => {
    m.validatePair.mockResolvedValue(validation())
    m.renderPng.mockResolvedValueOnce('blob:before').mockResolvedValueOnce('blob:after')
    render(<PairReview projectId="p1" before={asset('b1', 'before.tif', '2024-01-10T00:00:00Z')} after={asset('a1', 'after.tif', null)} inputType="upload" />)
    await userEvent.click(await screen.findByRole('button', { name: /Compare side by side/ }))
    await waitFor(() => expect(push).toHaveBeenCalledWith('/map'))
    expect(m.renderPng).toHaveBeenNthCalledWith(1, 'b1', [15.0, 40.6, 15.05, 40.64], 1536)
    expect(m.renderPng).toHaveBeenNthCalledWith(2, 'a1', [15.0, 40.6, 15.05, 40.64], 1536)  // same box => same pixel grid
    const q = useAppStore.getState().quickCompare!
    expect(q.bbox).toEqual([15.0, 40.6, 15.05, 40.64])
    expect(q.before).toMatchObject({ url: 'blob:before', label: 'before.tif', date: '2024-01-10T00:00:00Z' })
    expect(q.after).toMatchObject({ url: 'blob:after', label: 'after.tif', date: '' })  // no date is not invented
    expect(q.source).toEqual({ kind: 'upload', beforeAssetId: 'b1', afterAssetId: 'a1', projectId: 'p1' })
    expect(useAppStore.getState().viewMode).toBe('compare')
    expect(useAppStore.getState().flyRequest?.bbox).toEqual([15.0, 40.6, 15.05, 40.64])
  })

  it('is disabled when the pair cannot be processed and explains render failures', async () => {
    m.validatePair.mockResolvedValue(validation({ ok: false, issues: [{ level: 'error', code: 'no_overlap', message: 'The rasters do not overlap.', details: {} }] }))
    const { unmount } = render(<PairReview projectId="p1" before={asset('b1', 'a.tif', null)} after={asset('a1', 'b.tif', null)} inputType="upload" />)
    expect(await screen.findByRole('button', { name: /Compare side by side/ })).toBeDisabled()
    unmount()

    const { ApiError } = await import('@/lib/api')
    m.validatePair.mockResolvedValue(validation())
    m.renderPng.mockRejectedValue(new ApiError(422, 'bbox is outside the valid range.', 'bad_bbox'))
    render(<PairReview projectId="p1" before={asset('b2', 'a.tif', null)} after={asset('a2', 'b.tif', null)} inputType="upload" />)
    await userEvent.click(await screen.findByRole('button', { name: /Compare side by side/ }))
    await waitFor(() => expect(useAppStore.getState().toasts.some((t) => /outside the valid range/.test(t.text))).toBe(true))
    expect(useAppStore.getState().quickCompare).toBeNull()
    expect(push).not.toHaveBeenCalled()
  })
})
