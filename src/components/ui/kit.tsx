'use client'

import { Loader2, AlertTriangle, Inbox, FlaskConical } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn, SEVERITY_COLOR } from '@/lib/format'
import type { Severity } from '@/lib/api/types'

type Tone = 'default' | 'accent' | 'danger' | 'ghost'

const TONES: Record<Tone, string> = {
  default: 'border-ink-600 bg-ink-800 text-slate-200 hover:border-ink-500 hover:bg-ink-700',
  accent: 'border-accent-dim bg-accent-surface text-accent hover:border-accent/50 hover:bg-[#1a4430]',
  danger: 'border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20',
  ghost: 'border-transparent text-slate-400 hover:bg-ink-700 hover:text-slate-100',
}

export function Button({ tone = 'default', className, loading, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; loading?: boolean }) {
  return (
    <button {...props} disabled={props.disabled || loading} className={cn('btn', TONES[tone], className)}>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

/** Icon-only button: `label` is mandatory so every control has an accessible name and tooltip. */
export function IconButton({ label, active, children, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={cn(
        'focus-ring inline-flex h-8 w-8 items-center justify-center rounded-md border text-slate-400 transition-colors disabled:opacity-40',
        active ? 'border-accent-dim bg-accent-surface text-accent' : 'border-transparent hover:bg-ink-700 hover:text-slate-100',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label, size = 'md' }: {
  value: T; options: { value: T; label: ReactNode; title?: string; disabled?: boolean }[]; onChange: (v: T) => void; label: string; size?: 'sm' | 'md'
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-[color:var(--line-strong)] bg-black/30 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          title={o.title}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            'focus-ring rounded px-2.5 font-mono uppercase tracking-wider transition-colors disabled:opacity-35',
            size === 'sm' ? 'py-0.5 text-2xs' : 'py-1 text-xs2',
            value === o.value ? 'bg-accent/15 text-accent' : 'text-slate-400 hover:text-slate-100',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn('focus-ring relative h-4 w-7 shrink-0 rounded-full border transition-colors disabled:opacity-35', checked ? 'border-accent/50 bg-accent/30' : 'border-[color:var(--line-strong)] bg-white/[0.06]')}
    >
      <span className={cn('absolute top-[1px] h-3 w-3 rounded-full transition-all', checked ? 'left-[13px] bg-accent' : 'left-[1px] bg-slate-400')} />
    </button>
  )
}

export function Chip({ children, tone = 'default', className, title }: { children: ReactNode; tone?: 'default' | 'accent' | 'warn' | 'danger' | 'demo' | 'ok'; className?: string; title?: string }) {
  const tones = {
    default: 'border-[color:var(--line-strong)] bg-white/[0.04] text-slate-300',
    accent: 'border-accent/30 bg-accent-surface text-accent',
    warn: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
    danger: 'border-red-500/30 bg-red-500/10 text-red-300',
    ok: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
    demo: 'border-demo/40 bg-demo/10 text-demo',
  }
  return <span title={title} className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-[1px] font-mono text-2xs uppercase tracking-wider', tones[tone], className)}>{children}</span>
}

/** Always-visible marker for seeded / synthetic data so it can never be mistaken for a live result. */
export function DemoBadge({ className }: { className?: string }) {
  return (
    <Chip tone="demo" className={className} title="Synthetic demonstration data. Not real satellite imagery or a real detection.">
      <FlaskConical className="h-3 w-3" aria-hidden /> Demo data
    </Chip>
  )
}

export function SeverityDot({ severity, className }: { severity: Severity; className?: string }) {
  return <span aria-hidden className={cn('inline-block h-2 w-2 rounded-full', className)} style={{ background: SEVERITY_COLOR[severity], boxShadow: `0 0 8px ${SEVERITY_COLOR[severity]}66` }} />
}
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider" style={{ color: SEVERITY_COLOR[severity] }}>
      <SeverityDot severity={severity} /> {severity}
    </span>
  )
}

export function Stat({ label, value, sub, className }: { label: string; value: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="label">{label}</div>
      <div className="mt-0.5 truncate font-mono text-sm tabular-nums text-slate-100">{value}</div>
      {sub && <div className="mt-0.5 truncate text-2xs text-slate-500">{sub}</div>}
    </div>
  )
}

export function Section({ title, action, children, className }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('px-3 py-2.5 hairline-b last:border-b-0', className)}>
      <header className="mb-2 flex items-center justify-between gap-2">
        <h3 className="label">{title}</h3>
        {action}
      </header>
      {children}
    </section>
  )
}

export function Spinner({ className, label = 'Loading' }: { className?: string; label?: string }) {
  return <Loader2 role="status" aria-label={label} className={cn('h-4 w-4 animate-spin text-accent', className)} />
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded bg-white/[0.05]', className)} />
}

export function ProgressBar({ value, tone = 'accent', className, indeterminate }: { value: number; tone?: 'accent' | 'danger' | 'warn'; className?: string; indeterminate?: boolean }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  const color = tone === 'danger' ? 'bg-red-500' : tone === 'warn' ? 'bg-amber-400' : 'bg-accent'
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={indeterminate ? undefined : Math.round(pct)} className={cn('relative h-1 overflow-hidden rounded-full bg-white/[0.07]', className)}>
      {indeterminate ? <div className={cn('absolute inset-y-0 w-1/3 animate-scan rounded-full', color)} /> : <div className={cn('h-full rounded-full transition-[width] duration-500', color)} style={{ width: `${pct}%` }} />}
    </div>
  )
}

export function EmptyBlock({ title, hint, action, icon }: { title: string; hint?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
      <div className="text-slate-600">{icon ?? <Inbox className="h-6 w-6" aria-hidden />}</div>
      <div className="text-xs font-medium text-slate-300">{title}</div>
      {hint && <div className="max-w-xs text-xs2 text-slate-500">{hint}</div>}
      {action}
    </div>
  )
}

export function ErrorBlock({ title = 'Something went wrong', message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="m-3 rounded-md border border-red-500/25 bg-red-500/[0.06] p-3">
      <div className="flex items-center gap-2 text-xs font-medium text-red-300"><AlertTriangle className="h-3.5 w-3.5" aria-hidden /> {title}</div>
      <p className="mt-1 break-words text-xs2 text-slate-400">{message}</p>
      {onRetry && <Button tone="ghost" className="mt-2" onClick={onRetry}>Retry</Button>}
    </div>
  )
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="label block">{label}</label>
      {children}
      {hint && <p className="text-2xs text-slate-500">{hint}</p>}
    </div>
  )
}

export const inputCls = 'focus-ring w-full rounded-md border border-[color:var(--line-strong)] bg-black/30 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 disabled:opacity-50'
