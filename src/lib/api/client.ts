/**
 * Typed API client.
 *
 * Integrity rule: there is NO silent fallback to mock/demo data. A failed request surfaces as an `ApiError`
 * (status 0 = backend unreachable) and the UI shows an explicit error state.
 */

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const TOKEN_KEY = 'terratrack_access_token' // key kept from TerraTrack so existing sessions keep working

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
  get isNetwork(): boolean { return this.status === 0 }
  get isAuth(): boolean { return this.status === 401 }
  get isForbidden(): boolean { return this.status === 403 }
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  try { return window.localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(token: string | null): void {
  if (typeof window === 'undefined') return
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token)
    else window.localStorage.removeItem(TOKEN_KEY)
  } catch { /* storage unavailable (private mode) */ }
}

type Listener = () => void
const unauthorizedListeners = new Set<Listener>()
export function onUnauthorized(fn: Listener): () => void {
  unauthorizedListeners.add(fn)
  return () => unauthorizedListeners.delete(fn)
}

/** Extract a human-readable message from the backend's several error shapes. */
export function parseErrorBody(status: number, body: unknown): { message: string; code?: string; details?: unknown } {
  const fallback = `Request failed (${status}).`
  if (!body || typeof body !== 'object') return { message: fallback }
  const b = body as Record<string, unknown>
  const d = b.detail
  if (typeof d === 'string') return { message: d, details: b.errors }
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const o = d as Record<string, unknown>
    return { message: typeof o.message === 'string' ? o.message : fallback, code: typeof o.code === 'string' ? o.code : undefined, details: o }
  }
  if (Array.isArray(b.errors) && b.errors.length) {
    const first = b.errors[0] as { loc?: string[]; msg?: string }
    return { message: `${(first.loc ?? []).filter((p) => p !== 'body').join('.') || 'input'}: ${first.msg ?? 'invalid'}`, details: b.errors }
  }
  return { message: fallback }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null | (string | number)[]>
  /** return the raw Response (downloads) */
  raw?: boolean
  signal?: AbortSignal
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE}${path}`, typeof window === 'undefined' ? 'http://localhost' : window.location.origin)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === '') continue
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)))
      else url.searchParams.set(k, String(v))
    }
  }
  // API_BASE may be absolute (different origin): URL() keeps it; otherwise keep the path portion only.
  return API_BASE.startsWith('http') ? url.toString() : `${url.pathname}${url.search}`
}

export async function apiFetch<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, query, raw, headers, ...init } = opts
  const token = getToken()
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
        ...(headers as Record<string, string> | undefined),
      },
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err
    throw new ApiError(0, 'Cannot reach the GeoTrace backend. Check that the API is running.', 'network')
  }

  if (!response.ok) {
    let parsed: { message: string; code?: string; details?: unknown } = { message: `Request failed (${response.status}).` }
    try { parsed = parseErrorBody(response.status, await response.json()) } catch { /* non-JSON error body */ }
    if (response.status === 401) unauthorizedListeners.forEach((fn) => fn())
    throw new ApiError(response.status, parsed.message, parsed.code, parsed.details, response.headers.get('x-request-id'))
  }
  if (raw) return response as unknown as T
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Download a response body as a file (used for exports). Returns the number of features from the header when present. */
export async function downloadFile(path: string, opts: RequestOptions = {}, fallbackName = 'download'): Promise<{ filename: string; featureCount: number | null }> {
  const res = await apiFetch<Response>(path, { ...opts, raw: true })
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') ?? ''
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd)
  const filename = m ? decodeURIComponent(m[1]) : fallbackName
  const a = document.createElement('a')
  const url = URL.createObjectURL(blob)
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
  const fc = res.headers.get('x-feature-count')
  return { filename, featureCount: fc === null ? null : Number(fc) }
}

/** Auth header for raster-tile requests issued by MapLibre / Cesium (tiles are access controlled). */
export function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

/** Absolute tile URL template for an analysis raster layer. */
export function analysisTileUrl(analysisId: string, layer: 'before' | 'after' | 'score' | 'mask' | 'delta_ndvi' | 'ndvi_before' | 'ndvi_after', opts: { falseColor?: boolean } = {}): string {
  const base = API_BASE.startsWith('http') ? API_BASE : `${typeof window === 'undefined' ? '' : window.location.origin}${API_BASE}`
  return `${base}/analyses/${analysisId}/tiles/${layer}/{z}/{x}/{y}.png${opts.falseColor ? '?false_color=true' : ''}`
}
export function assetTileUrl(assetId: string): string {
  const base = API_BASE.startsWith('http') ? API_BASE : `${typeof window === 'undefined' ? '' : window.location.origin}${API_BASE}`
  return `${base}/imagery/${assetId}/tiles/{z}/{x}/{y}.png`
}
export function isApiTileUrl(url: string): boolean {
  return url.startsWith(API_BASE) || (API_BASE.startsWith('/') && url.includes(API_BASE))
}
