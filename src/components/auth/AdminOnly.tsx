'use client'

import Link from 'next/link'
import { isAdmin } from '@/lib/auth'
import { useAppStore } from '@/store/useAppStore'

/** Renders children only for administrators (the backend enforces the same rule on every endpoint). */
export default function AdminOnly({ children }: { children: React.ReactNode }) {
  const role = useAppStore((s) => s.authUser?.role)
  if (!isAdmin(role)) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <div>
          <h1 className="text-lg font-semibold text-accent">Access denied</h1>
          <p className="mt-2 text-xs text-slate-400">This area is restricted to administrators.</p>
          <Link href="/map" className="btn mt-4 border-accent/40 bg-accent/10 text-accent">Back to the map</Link>
        </div>
      </div>
    )
  }
  return <>{children}</>
}
