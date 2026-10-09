'use client'

import { X } from 'lucide-react'
import { useBootstrap } from '@/hooks/useBootstrap'
import { cn } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import AuthGate from '@/components/auth/AuthGate'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { ErrorBlock } from '@/components/ui/kit'
import GeoGuider from '@/components/geoguider/GeoGuider'

function Toasts() {
  const toasts = useAppStore((s) => s.toasts)
  const dismiss = useAppStore((s) => s.dismissToast)
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-10 right-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} role="status" className={cn('panel-solid pointer-events-auto flex animate-slide-in items-start gap-2 rounded-md px-3 py-2 text-xs shadow-xl shadow-black/60',
          t.kind === 'error' ? 'border-red-500/40 text-red-200' : t.kind === 'success' ? 'border-emerald-400/30 text-emerald-100' : 'text-slate-200')}>
          <span className="flex-1 break-words">{t.text}</span>
          <button onClick={() => dismiss(t.id)} aria-label="Dismiss notification" className="focus-ring rounded text-slate-500 hover:text-slate-200"><X className="h-3.5 w-3.5" /></button>
        </div>
      ))}
    </div>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  const { refresh } = useBootstrap()
  const systemError = useAppStore((s) => s.systemError)
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-ink-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        {systemError && (
          <div className="hairline-b bg-red-500/[0.05]"><ErrorBlock title="Backend unavailable" message={`${systemError} Nothing shown below is substituted with sample data.`} onRetry={() => void refresh()} /></div>
        )}
        <main className="relative min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
      <Toasts />
      <GeoGuider />
    </div>
  )
}

export default function AppShell({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  return (
    <AuthGate adminOnly={adminOnly}>
      <Frame>{children}</Frame>
    </AuthGate>
  )
}
