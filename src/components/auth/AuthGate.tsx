'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { api, ApiError, onUnauthorized } from '@/lib/api'
import { getProtectedRouteState } from '@/lib/auth'
import { toAuthUser, useAppStore } from '@/store/useAppStore'
import { Spinner, ErrorBlock, Button } from '@/components/ui/kit'
import LoginScreen from './LoginScreen'

/**
 * Session guard. Validates the stored token against the backend (no demo role, no local fake session).
 * Distinguishes "not signed in" from "backend unreachable" so an outage is never presented as a login prompt.
 */
export default function AuthGate({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  const authStatus = useAppStore((s) => s.authStatus)
  const authUser = useAppStore((s) => s.authUser)
  const setAuthUser = useAppStore((s) => s.setAuthUser)
  const signOut = useAppStore((s) => s.signOut)
  const [networkError, setNetworkError] = useState<string | null>(null)

  useEffect(() => onUnauthorized(() => { api.logout(); signOut() }), [signOut])

  useEffect(() => {
    if (authStatus !== 'loading') return
    if (!api.hasToken()) { setAuthUser(null); return }
    let cancelled = false
    api.me()
      .then((me) => { if (!cancelled) setAuthUser(toAuthUser(me)) })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.isNetwork) setNetworkError(err.message)
        else { api.logout(); setAuthUser(null) }
      })
    return () => { cancelled = true }
  }, [authStatus, setAuthUser, setNetworkError])

  if (networkError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-950 p-6">
        <div className="panel-solid max-w-sm rounded-lg">
          <ErrorBlock title="Backend unreachable" message={networkError} />
          <div className="px-3 pb-3"><Button onClick={() => { setNetworkError(null); useAppStore.getState().setAuthStatus('loading') }}>Retry</Button></div>
        </div>
      </div>
    )
  }

  const state = getProtectedRouteState(authStatus, authUser?.role ?? null, adminOnly)
  if (state === 'loading') {
    return <div className="flex min-h-screen items-center justify-center bg-ink-950 text-slate-500"><Spinner label="Checking session" /></div>
  }
  if (state === 'login') return <LoginScreen />
  if (state === 'forbidden') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-950 p-6 text-center">
        <div>
          <h1 className="text-lg font-semibold text-accent">Access denied</h1>
          <p className="mt-2 text-xs text-slate-400">This area is restricted to administrators.</p>
          <Link href="/map" className="btn mt-4 border-accent-dim bg-accent-surface text-accent">Back to the map</Link>
        </div>
      </div>
    )
  }
  return <>{children}</>
}
