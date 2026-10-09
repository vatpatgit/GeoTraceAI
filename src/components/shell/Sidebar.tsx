'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { BarChart3, Bell, ChevronsLeft, ChevronsRight, FileText, Flame, Gauge, Globe2, Layers, Leaf, MapPin, ScanSearch, Settings, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { isAdmin } from '@/lib/auth'
import { isActiveStatus, cn } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Logo } from './Logo'

interface Item { id: string; label: string; icon: React.ComponentType<{ className?: string }>; href?: string; layerGroup?: 'environmental' | 'risk'; badge?: number | null }
interface Group { title: string; items: Item[] }

export default function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const user = useAppStore((s) => s.authUser)
  const analyses = useAppStore((s) => s.analyses)
  const setLeftPanel = useAppStore((s) => s.setLeftPanel)
  const [expanded, setExpanded] = useState(false)
  const [unresolved, setUnresolved] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    const load = () => api.alerts.stats().then((s) => alive && setUnresolved(s.unresolved)).catch(() => alive && setUnresolved(null))
    load()
    const t = setInterval(load, 20_000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const running = analyses.filter((a) => isActiveStatus(a.status)).length
  const groups: Group[] = [
    { title: 'Workspace', items: [
      { id: 'overview', label: 'Overview', icon: Gauge, href: '/dashboard' },
      { id: 'map', label: 'Globe / Map', icon: Globe2, href: '/map' },
      { id: 'analyses', label: 'Analyses', icon: Layers, href: '/analyses', badge: running || null },
      { id: 'regions', label: 'Monitored regions', icon: MapPin, href: '/regions' },
    ] },
    { title: 'Layers', items: [
      { id: 'env', label: 'Environmental layers', icon: Leaf, layerGroup: 'environmental' },
      { id: 'risk', label: 'Risk assessment', icon: Flame, layerGroup: 'risk' },
    ] },
    { title: 'Intelligence', items: [
      { id: 'changes', label: 'Change intelligence', icon: ScanSearch, href: '/changes' },
      { id: 'alerts', label: 'Alerts', icon: Bell, href: '/alerts', badge: unresolved || null },
      { id: 'analytics', label: 'Analytics', icon: BarChart3, href: '/analytics' },
      { id: 'reports', label: 'Reports', icon: FileText, href: '/reports' },
    ] },
    { title: 'System', items: [
      { id: 'settings', label: 'Settings', icon: Settings, href: '/settings' },
      ...(isAdmin(user?.role) ? [{ id: 'admin', label: 'User administration', icon: ShieldCheck, href: '/admin/users' }] : []),
    ] },
  ]

  function onItem(item: Item) {
    if (item.layerGroup) {
      useAppStore.setState({ layerFocus: item.layerGroup })
      setLeftPanel('layers')
      if (pathname !== '/map') router.push('/map')
    }
  }

  return (
    <aside aria-label="Primary navigation" className={cn('hairline-b z-30 flex shrink-0 flex-col border-r border-[color:var(--line)] bg-ink-900 transition-[width] duration-200', expanded ? 'w-56' : 'w-12')}>
      <div className="flex h-11 items-center gap-2 border-b border-[color:var(--line)] px-2.5">
        <Logo className="h-6 w-6 shrink-0" />
        {expanded && <span className="text-sm font-semibold tracking-tight text-slate-100">GeoTrace</span>}
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-1.5">
        {groups.map((g) => (
          <div key={g.title} className="mb-1">
            {expanded ? <div className="label px-3 pb-1 pt-2">{g.title}</div> : <div className="mx-3 my-1.5 h-px bg-white/[0.05]" />}
            {g.items.map((item) => {
              const active = item.href ? pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href)) : false
              const Icon = item.icon
              const body = (
                <>
                  <span className="relative">
                    <Icon className="h-4 w-4 shrink-0" />
                    {item.badge ? <span className="absolute -right-1.5 -top-1.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-accent px-1 font-mono text-[9px] font-bold text-ink-950">{item.badge > 99 ? '99+' : item.badge}</span> : null}
                  </span>
                  {expanded && <span className="truncate text-xs">{item.label}</span>}
                </>
              )
              const cls = cn('focus-ring relative mx-1.5 flex h-8 items-center gap-2.5 rounded-md px-2.5 text-slate-400 transition-colors hover:bg-ink-700 hover:text-slate-100', active && 'bg-accent-surface text-accent')
              return item.href ? (
                <Link key={item.id} href={item.href} title={item.label} aria-label={item.label} aria-current={active ? 'page' : undefined} className={cls}>
                  {active && <span className="absolute -left-1.5 top-1.5 h-5 w-[2px] rounded-full bg-accent" />}
                  {body}
                </Link>
              ) : (
                <button key={item.id} title={item.label} aria-label={item.label} onClick={() => onItem(item)} className={cn(cls, 'w-[calc(100%-0.75rem)] text-left')}>{body}</button>
              )
            })}
          </div>
        ))}
      </nav>
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        title={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        className="focus-ring m-1.5 flex h-8 items-center justify-center rounded-md text-slate-500 hover:bg-ink-700 hover:text-slate-200"
      >
        {expanded ? <ChevronsLeft className="h-4 w-4" /> : <ChevronsRight className="h-4 w-4" />}
      </button>
    </aside>
  )
}
