import type { BoundingBox } from '@/types'

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')

export class SentinelApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export interface FetchSentinelImageryOptions {
  width?: number
  height?: number
}

/** MapLibre image-source corners: top-left, top-right, bottom-right, bottom-left. */
export function bboxToImageCoordinates(
  bbox: BoundingBox,
): [[number, number], [number, number], [number, number], [number, number]] {
  return [
    [bbox.minLon, bbox.maxLat],
    [bbox.maxLon, bbox.maxLat],
    [bbox.maxLon, bbox.minLat],
    [bbox.minLon, bbox.minLat],
  ]
}

function getAccessToken(): string | null {
  if (typeof globalThis.localStorage === 'undefined') return null
  return globalThis.localStorage.getItem('terratrack_access_token')
}

export async function fetchSentinelImagery(
  regionId: string,
  date: string,
  options: FetchSentinelImageryOptions = {},
): Promise<Blob> {
  const token = getAccessToken()
  if (!token) {
    throw new SentinelApiError(401, 'Authentication required for Sentinel imagery.')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}/sentinel/imagery`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        Accept: 'image/png',
      },
      body: JSON.stringify({
        region_id: regionId,
        date,
        width: options.width ?? 1024,
        height: options.height ?? 1024,
        format: 'image/png',
      }),
    })
  } catch {
    throw new SentinelApiError(0, 'Unable to reach the Sentinel imagery service.')
  }

  if (!response.ok) {
    let message = `Sentinel imagery request failed (${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // Keep the status-based message.
    }
    throw new SentinelApiError(response.status, message)
  }

  return response.blob()
}
