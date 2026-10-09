import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore, type PlainImage } from '@/store/useAppStore'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
const m = vi.hoisted(() => ({ upload: vi.fn(), plainMl: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, imagery: { ...actual.api.imagery, upload: m.upload, plainMlChanges: m.plainMl } } }
})
import UploadSlot from './UploadSlot'
import PlainPairStep from './PlainPairStep'
import ImageCompareView from '@/components/map/ImageCompareView'

const img = (name: string, w = 800, h = 600): PlainImage => ({ file: new File(['x'], name, { type: 'image/png' }), url: `blob:${name}`, name, width: w, height: h })

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ plainCompare: null })
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }))
  // jsdom never decodes images: report a fixed natural size once a src is set
  class FakeImage { onload: (() => void) | null = null; onerror: (() => void) | null = null; naturalWidth = 640; naturalHeight = 480
    set src(_v: string) { setTimeout(() => this.onload?.(), 0) } }
  vi.stubGlobal('Image', FakeImage)
})

describe('UploadSlot accepts ordinary images', () => {
  it.each(['photo.png', 'photo.jpg', 'photo.JPEG', 'photo.webp', 'photo.bmp', 'photo.gif'])('keeps %s in the browser (no server upload) and reports its size', async (name) => {
    const onPlain = vi.fn()
    render(<UploadSlot title="Before" projectId="p" asset={null} onAsset={() => {}} plain={null} onPlain={onPlain} />)
    fireEvent.change(screen.getByLabelText('Before GeoTIFF file'), { target: { files: [new File(['x'], name, { type: '' })] } })
    await waitFor(() => expect(onPlain).toHaveBeenCalledWith(expect.objectContaining({ name, width: 640, height: 480 })))
    expect(m.upload).not.toHaveBeenCalled()
  })

  it('still sends GeoTIFFs to the server', async () => {
    const { ApiError } = await import('@/lib/api')
    m.upload.mockRejectedValue(new ApiError(422, 'The file is not a valid GeoTIFF.'))
    const onPlain = vi.fn()
    render(<UploadSlot title="Before" projectId="p" asset={null} onAsset={() => {}} plain={null} onPlain={onPlain} />)
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText('Before GeoTIFF file'), new File(['x'], 'scene.tif'))
    expect(await screen.findByText('The file is not a valid GeoTIFF.')).toBeInTheDocument()
    expect(m.upload).toHaveBeenCalledTimes(1)
    expect(onPlain).not.toHaveBeenCalled()
  })

  it('rejects other file types with a message naming what is accepted', async () => {
    render(<UploadSlot title="Before" projectId="p" asset={null} onAsset={() => {}} plain={null} onPlain={vi.fn()} />)
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText('Before GeoTIFF file'), new File(['x'], 'notes.pdf'))
    expect(await screen.findByText(/GeoTIFF \(\.tif \/ \.tiff\) or an image/)).toBeInTheDocument()
    expect(m.upload).not.toHaveBeenCalled()
  })

  it('without the image option (other callers) only GeoTIFFs are accepted', async () => {
    render(<UploadSlot title="After" projectId="p" asset={null} onAsset={() => {}} />)
    expect(screen.getByLabelText('After GeoTIFF file')).toHaveAttribute('accept', '.tif,.tiff,image/tiff')
    fireEvent.change(screen.getByLabelText('After GeoTIFF file'), { target: { files: [new File(['x'], 'a.png')] } })
    expect(await screen.findByRole('alert')).toHaveTextContent(/Choose a GeoTIFF/)
  })
})

describe('PlainPairStep', () => {
  it('opens the image comparison once both images are in', async () => {
    render(<PlainPairStep before={img('a.jpg')} after={img('b.png')} />)
    await waitFor(() => expect(push).toHaveBeenCalledWith('/image-compare'))
    expect(useAppStore.getState().plainCompare?.before.name).toBe('a.jpg')
  })
  it('refuses images with different proportions and says what to do', () => {
    render(<PlainPairStep before={img('a.jpg', 800, 600)} after={img('b.png', 600, 800)} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/different proportions/)
    expect(push).not.toHaveBeenCalled()
  })
})

describe('ImageCompareView', () => {
  const fc = {
    type: 'FeatureCollection' as const,
    features: [{ type: 'Feature' as const, id: 1, geometry: { type: 'Polygon', coordinates: [[[10, 10], [60, 10], [60, 50], [10, 50], [10, 10]]] }, properties: { id: 1, area_px: 2000, area_m2: null, point: [35, 30] as [number, number], magnitude: 0.8 } }],
    metadata: { model_id: 'levir-cd-v1', model_name: 'LEVIR', input_pixel_size_m: 2, model_fed_at_m: 2, masked_cloud_pct: 0, feature_count: 1, returned: 1, total_changed_area_m2: null, warnings: [], notes: [],
      disclaimer: 'Model-inferred candidates.', timings_s: {}, stats: { analyzed_area_m2: 0, changed_fraction: 0.0042, largest_m2: 0, median_m2: 0, size_classes: [{ label: '< 0.05% of image', count: 1, area_m2: 0 }] },
      image_size: [800, 600] as [number, number], pixel_size_known: false, pixel_size_m: null, model_choice_reason: 'native scale', total_changed_px: 2000, source: 'uploaded images (not georeferenced)' },
  }

  it('shows an empty state with a way back when there is nothing to compare', () => {
    render(<ImageCompareView />)
    expect(screen.getByText('No images to compare')).toBeInTheDocument()
  })

  it('draws the detections in image-pixel space on the after image and reports shares, not invented square metres', async () => {
    m.plainMl.mockResolvedValue(fc)
    useAppStore.setState({ plainCompare: { before: img('a.jpg'), after: img('b.png') } })
    render(<ImageCompareView />)
    expect(screen.getByRole('slider', { name: 'Before and after comparison position' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('switch', { name: 'Show changes detected by the ML model' }))
    await waitFor(() => expect(m.plainMl).toHaveBeenCalledTimes(1))
    expect(m.plainMl.mock.calls[0][2]).toEqual({ pixelSizeM: null })
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent(/1 area flagged · 0\.42% of the image/)
    expect(status).not.toHaveTextContent(/m²/)
    const svg = screen.getByLabelText('Detected changes')
    expect(svg).toHaveAttribute('viewBox', '0 0 800 600')
    expect(svg.querySelectorAll('path')).toHaveLength(1)
  })

  it('passes a user-supplied pixel size and shows backend errors visibly', async () => {
    const { ApiError } = await import('@/lib/api')
    m.plainMl.mockRejectedValue(new ApiError(422, 'The after file is not a readable image.', 'not_an_image'))
    useAppStore.setState({ plainCompare: { before: img('a.jpg'), after: img('b.png') } })
    render(<ImageCompareView />)
    await userEvent.type(screen.getByLabelText('Pixel size in metres'), '0.3')
    await userEvent.click(screen.getByRole('switch', { name: 'Show changes detected by the ML model' }))
    await waitFor(() => expect(m.plainMl).toHaveBeenCalled())
    expect(m.plainMl.mock.calls[0][2]).toEqual({ pixelSizeM: 0.3 })
    expect(await screen.findByRole('alert')).toHaveTextContent(/not a readable image/)
  })
})
