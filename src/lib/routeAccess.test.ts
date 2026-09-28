import { describe, expect, it } from 'vitest'
import { getProtectedRouteState } from './routeAccess'

describe('protected route access', () => {
  it('waits for authentication hydration', () => {
    expect(getProtectedRouteState('loading', null)).toBe('loading')
  })

  it('sends unauthenticated users to login', () => {
    expect(getProtectedRouteState('unauthenticated', null)).toBe('login')
  })

  it.each(['Admin', 'Researcher', 'Viewer'] as const)('%s can access normal routes', (role) => {
    expect(getProtectedRouteState('authenticated', role)).toBe('allowed')
  })

  it('allows only administrators into admin routes', () => {
    expect(getProtectedRouteState('authenticated', 'Admin', true)).toBe('allowed')
    expect(getProtectedRouteState('authenticated', 'Researcher', true)).toBe('forbidden')
    expect(getProtectedRouteState('authenticated', 'Viewer', true)).toBe('forbidden')
  })
})