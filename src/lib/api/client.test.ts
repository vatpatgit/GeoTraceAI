import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, buildUrl, getToken, onUnauthorized, parseErrorBody, setToken } from './client'
import { filterQuery } from './index'

describe('parseErrorBody', () => {
  it('reads FastAPI string details', () => {
    expect(parseErrorBody(404, { detail: 'Not found' }).message).toBe('Not found')
  })
  it('reads structured {code,message} details', () => {
    const p = parseErrorBody(422, { detail: { code: 'too_many_pixels', message: 'Reduce the area of interest.' } })
    expect(p.code).toBe('too_many_pixels')
    expect(p.message).toBe('Reduce the area of interest.')
  })
  it('summarises validation error arrays with the field path', () => {
    const p = parseErrorBody(422, { errors: [{ loc: ['body', 'min_area_m2'], msg: 'must be >= 0' }] })
    expect(p.message).toBe('min_area_m2: must be >= 0')
  })
  it('falls back to a generic message for unknown bodies', () => {
    expect(parseErrorBody(500, null).message).toContain('500')
    expect(parseErrorBody(500, 'oops').message).toContain('500')
  })
})

describe('buildUrl / filterQuery', () => {
  it('repeats array params and drops empty values', () => {
    const url = buildUrl('/x', { severity: ['high', 'critical'], q: '', n: undefined, limit: 5 })
    expect(url).toContain('severity=high&severity=critical')
    expect(url).toContain('limit=5')
    expect(url).not.toContain('q=')
  })
  it('serialises bbox comma separated', () => {
    expect(filterQuery({ bbox: [1, 2, 3, 4] }).bbox).toBe('1,2,3,4')
  })
})

describe('apiFetch', () => {
  beforeEach(() => setToken('tok'))
  afterEach(() => { vi.unstubAllGlobals(); setToken(null) })

  it('sends the bearer token and parses JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await apiFetch('/ping')).toEqual({ ok: 1 })
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer tok' })
  })

  it('surfaces an unreachable backend as an explicit network error instead of fake data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await apiFetch('/analyses').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).isNetwork).toBe(true)
  })

  it('maps HTTP errors to ApiError and notifies 401 listeners', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Not authenticated' }), { status: 401 })))
    const seen = vi.fn()
    const off = onUnauthorized(seen)
    const err = await apiFetch('/me').catch((e) => e)
    off()
    expect(err).toMatchObject({ status: 401, message: 'Not authenticated' })
    expect(seen).toHaveBeenCalledTimes(1)
  })

  it('returns undefined for 204', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    expect(await apiFetch('/x', { method: 'DELETE' })).toBeUndefined()
  })
})

describe('token storage', () => {
  it('round-trips and clears', () => {
    setToken('abc')
    expect(getToken()).toBe('abc')
    setToken(null)
    expect(getToken()).toBeNull()
  })
})
