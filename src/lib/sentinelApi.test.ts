import { describe, expect, it, vi, beforeEach } from 'vitest'
import { bboxToImageCoordinates, fetchSentinelImagery, SentinelApiError } from './sentinelApi'

describe('sentinelApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn())
    Object.defineProperty(globalThis, 'localStorage', {
      value: { getItem: () => 'test-token' },
      configurable: true,
    })
  })

  it('maps region bbox to MapLibre image coordinates', () => {
    expect(
      bboxToImageCoordinates({ minLon: -70, minLat: -5, maxLon: -60, maxLat: 5 }),
    ).toEqual([
      [-70, 5],
      [-60, 5],
      [-60, -5],
      [-70, -5],
    ])
  })

  it('requests imagery for the selected region and date with auth', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(new Blob(['png-bytes'], { type: 'image/png' }), {
        status: 200,
        headers: { 'Content-Type': 'image/png' },
      }),
    )

    const blob = await fetchSentinelImagery('region-uuid-1', '2024-01-15')
    expect(blob.type).toBe('image/png')
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/sentinel/imagery'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
        body: JSON.stringify({
          region_id: 'region-uuid-1',
          date: '2024-01-15',
          width: 1024,
          height: 1024,
          format: 'image/png',
        }),
      }),
    )
  })

  it('does not return fake imagery when unauthenticated', async () => {
    Object.defineProperty(globalThis, 'localStorage', {
      value: { getItem: () => null },
      configurable: true,
    })

    await expect(fetchSentinelImagery('region-uuid-1', '2024-01-15')).rejects.toMatchObject({
      status: 401,
    })
    expect(fetch).not.toHaveBeenCalled()
  })

  it('returns a PNG blob without fabricating fallback imagery on success', async () => {
    const pngBytes = new Uint8Array([137, 80, 78, 71])
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(new Blob([pngBytes], { type: 'image/png' }), {
        status: 200,
        headers: { 'Content-Type': 'image/png' },
      }),
    )

    const blob = await fetchSentinelImagery('region-uuid-1', '2024-01-15')
    expect(blob.size).toBe(pngBytes.length)
    expect(blob.type).toBe('image/png')
  })

  it('surfaces backend Sentinel errors', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Sentinel Hub error: unauthorized' }), { status: 502 }),
    )

    await expect(fetchSentinelImagery('region-uuid-1', '2024-01-15')).rejects.toEqual(
      expect.objectContaining<SentinelApiError>({
        status: 502,
        message: 'Sentinel Hub error: unauthorized',
      }),
    )
  })
})
