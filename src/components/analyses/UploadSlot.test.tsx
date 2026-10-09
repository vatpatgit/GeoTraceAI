import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ImageryAsset } from '@/lib/api'

const m = vi.hoisted(() => ({ upload: vi.fn(), update: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, imagery: { ...actual.api.imagery, upload: m.upload, update: m.update } } }
})

import UploadSlot from './UploadSlot'

const asset = (over: Partial<ImageryAsset> = {}): ImageryAsset => ({
  id: 'x1', project_id: 'p', kind: 'upload', original_filename: 'before.tif', size_bytes: 1_048_576, width: 512, height: 512, band_count: 4, dtype: 'uint16', crs_epsg: 32633,
  pixel_size_m: 10, nodata: 0, footprint: { type: 'Polygon', coordinates: [] }, bounds: [0, 0, 1, 1], band_descriptions: null, band_map: { blue: 1, green: 2, red: 3, nir: 4 },
  band_map_confirmed: false, band_notes: [], acquisition_start: null, acquisition_end: null, cloud_cover_pct: null, source_provider: null, source_product_id: null, sha256: 'abc', is_demo: false,
  warnings: [{ level: 'warning', code: 'no_date', message: 'No acquisition date was found.', details: {} }], created_at: '', ...over,
})

beforeEach(() => vi.clearAllMocks())

describe('UploadSlot', () => {
  it('rejects non-TIFF files client-side without calling the API', async () => {
    render(<UploadSlot title="Before" projectId="p" asset={null} onAsset={() => {}} />)
    const input = screen.getByLabelText('Before GeoTIFF file') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'photo.png', { type: 'image/png' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent(/Choose a GeoTIFF/)
    expect(m.upload).not.toHaveBeenCalled()
  })

  it('uploads a GeoTIFF and hands the server-validated asset to the parent', async () => {
    m.upload.mockResolvedValue(asset())
    const onAsset = vi.fn()
    render(<UploadSlot title="Before" projectId="p" asset={null} onAsset={onAsset} />)
    fireEvent.change(screen.getByLabelText('Before GeoTIFF file'), { target: { files: [new File(['II*'], 'before.tif', { type: 'image/tiff' })] } })
    await waitFor(() => expect(onAsset).toHaveBeenCalledWith(expect.objectContaining({ id: 'x1' })))
    expect(m.upload).toHaveBeenCalledWith(expect.any(File), 'p', expect.any(Object))
  })

  it('shows a server rejection message verbatim', async () => {
    const { ApiError } = await import('@/lib/api')
    m.upload.mockRejectedValue(new ApiError(422, 'The file is not a valid GeoTIFF.', 'not_a_geotiff'))
    render(<UploadSlot title="After" projectId="p" asset={null} onAsset={() => {}} />)
    fireEvent.change(screen.getByLabelText('After GeoTIFF file'), { target: { files: [new File(['x'], 'fake.tif')] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('The file is not a valid GeoTIFF.')
  })

  it('reports georeferencing, flags assumed band roles and lets the user change them', async () => {
    m.update.mockResolvedValue(asset({ band_map_confirmed: true }))
    const onAsset = vi.fn()
    render(<UploadSlot title="Before" projectId="p" asset={asset()} onAsset={onAsset} />)
    expect(screen.getByText('EPSG:32633')).toBeInTheDocument()
    expect(screen.getByText('10.00 m / px')).toBeInTheDocument()
    expect(screen.getByText(/assumed - please confirm/)).toBeInTheDocument()
    expect(screen.getByText('No acquisition date was found.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Before nir band'), '3')
    await waitFor(() => expect(m.update).toHaveBeenCalledWith('x1', { band_map: expect.objectContaining({ nir: 3 }) }))
  })
})
