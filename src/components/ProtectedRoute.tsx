'use client'

import Link from 'next/link'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAppStore } from '@/store/useAppStore'
import { fetchCurrentUser } from '@/lib/mockApi'
import AuthMock from './AuthMock'
import { getProtectedRouteState } from '@/lib/routeAccess'

interface ProtectedRouteProps {
    children: React.ReactNode
    adminOnly?: boolean
}

export default function ProtectedRoute({ children, adminOnly = false }: ProtectedRouteProps) {
    const router = useRouter()
    const { authStatus, authUser, setAuthStatus, setAuthUser, setUserRole } = useAppStore()

    useEffect(() => {
        if (authStatus !== 'loading') return

        let cancelled = false
        fetchCurrentUser().then((user) => {
            if (cancelled) return
            if (user) {
                setAuthUser(user)
                setUserRole(user.role)
            } else {
                setAuthStatus('unauthenticated')
            }
        })

        return () => {
            cancelled = true
        }
    }, [authStatus, setAuthStatus, setAuthUser, setUserRole])

    useEffect(() => {
        if (authStatus === 'unauthenticated' && window.location.pathname !== '/dashboard') {
            router.replace('/dashboard')
        }
    }, [authStatus, router])

    const routeState = getProtectedRouteState(authStatus, authUser?.role ?? null, adminOnly)

    if (routeState === 'loading') {
        return <div className="min-h-screen bg-background flex items-center justify-center text-slate-400">Checking your session...</div>
    }

    if (routeState === 'login') {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center p-6">
                <div className="text-center max-w-md">
                    <h1 className="text-2xl font-semibold text-white">Sign in to TerraTrack</h1>
                    <p className="mt-2 text-sm text-slate-400">Your session is required to access this workspace.</p>
                    <AuthMock />
                </div>
            </div>
        )
    }

    if (routeState === 'forbidden') {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center p-6">
                <div className="text-center max-w-md">
                    <h1 className="text-3xl font-semibold text-accent">Access Denied</h1>
                    <p className="mt-3 text-slate-300">You do not have permission to access this page.</p>
                    <Link href="/dashboard" className="inline-block mt-6 rounded-lg bg-accent px-4 py-2 font-medium text-background">Return to Dashboard</Link>
                </div>
            </div>
        )
    }

    return <>{children}</>
}
