'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/format'

/** Scrollable full-page container with a consistent title block for the non-map pages. */
export default function PageFrame({ title, subtitle, actions, children, wide = false }: { title: string; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className={cn('mx-auto space-y-4 p-5', wide ? 'max-w-7xl' : 'max-w-5xl')}>
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-slate-100">{title}</h1>
            {subtitle && <p className="mt-0.5 max-w-2xl text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
        {children}
      </div>
    </div>
  )
}

export function Card({ title, children, className, action }: { title?: string; children: ReactNode; className?: string; action?: ReactNode }) {
  return (
    <section className={cn('rounded-md border border-white/[0.07] bg-ink-900/60', className)}>
      {title && (
        <header className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
          <h2 className="label">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-3">{children}</div>
    </section>
  )
}
