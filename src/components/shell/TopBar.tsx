'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertCircle, CalendarRange, ChevronDown, LogOut, Radio, Search, Square, User } from 'lucide-react'
import { api } from '@/lib/api'
import { roleLabel } from '@/lib/auth'
import { cn, formatDate, STATUS_LABEL, isActiveStatus } from '@/lib/format'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { Chip, DemoBadge, ProgressBar } from '@/components/ui/kit'

function useOutside(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  return ref
}

function Dropdown({ label, trigger, children, align = 'left', width = 'w-72' }: { label: string; trigger: React.ReactNode; children: (close: () => void) => React.ReactNode; align?: 'left' | 'right'; width?: string }) {
  const [open, setOpen] = useState(false)
  const ref = useOutside(open, () => setOpen(false))
  return (
    <div ref={ref} className="relative">
      <button aria-haspopup="listbox" aria-expanded={open} aria-label={label} onClick={() => setOpen((v) => !v)} className="focus-ring flex h-7 max-w-[220px] items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.03] px-2 text-xs text-slate-200 hover:bg-white/[0.07]">
        {trigger}
        <ChevronDown className="h-3 w-3 shrink-0 text-slate-500" />
      </button>
      {open && (
        <div role="listbox" aria-label={label} className={cn('panel-solid absolute top-9 z-50 max-h-80 overflow-y-auto rounded-md py-1 shadow-2xl shadow-black/70', width, align === 'right' ? 'right-0' : 'left-0')}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

function Option({ active, onClick, children }: { active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button role="option" aria-selected={!!active} onClick={onClick} className={cn('focus-ring flex w-full items-start gap-2 px-3 py-1.5 text-left text-xs hover:bg-white/[0.06]', active ? 'text-accent' : 'text-slate-300')}>
      {children}
    </button>
  )
}

const COORD_RE = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/

export default function TopBar() {
  const router = useRouter()
  const user = useAppStore((s) => s.authUser)
  const signOut = useAppStore((s) => s.signOut)
  const projects = useAppStore((s) => s.projects)
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const setActiveProject = useAppStore((s) => s.setActiveProject)
  const analyses = useAppStore((s) => s.analyses)
  const analysis = useAppStore(selectActiveAnalysis)
  const setActiveAnalysis = useAppStore((s) => s.setActiveAnalysis)
  const system = useAppStore((s) => s.system)
  const systemError = useAppStore((s) => s.systemError)
  const requestFly = useAppStore((s) => s.requestFly)
  const setViewMode = useAppStore((s) => s.setViewMode)
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const searchRef = useOutside(searchOpen, () => setSearchOpen(false))

  const project = projects.find((p) => p.id === activeProjectId)
  const projectAnalyses = useMemo(() => analyses.filter((a) => !activeProjectId || a.project_id === activeProjectId), [analyses, activeProjectId])

  const coord = COORD_RE.exec(query)
  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q || coord) return []
    return analyses.filter((a) => a.name.toLowerCase().includes(q)).slice(0, 6)
  }, [query, analyses, coord])

  function submitSearch(e: React.FormEvent) {
    e.preventDefault()
    if (coord) {
      const lat = parseFloat(coord[1]); const lon = parseFloat(coord[2])
      if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
        requestFly({ center: [lon, lat], zoom: 12 })
        router.push('/map')
        setSearchOpen(false)
      }
    } else if (results[0]) {
      setActiveAnalysis(results[0].id); router.push('/map'); setSearchOpen(false)
    }
  }

  const backend: { tone: 'ok' | 'danger' | 'warn'; text: string } = systemError
    ? { tone: 'danger', text: 'Backend offline' }
    : !system ? { tone: 'warn', text: 'Connecting' }
    : !system.database.ok ? { tone: 'danger', text: 'Database down' }
    : { tone: 'ok', text: 'Backend online' }

  const running = analysis && isActiveStatus(analysis.status)

  return (
    <header className="hairline-b relative z-20 flex h-11 shrink-0 items-center gap-3 bg-ink-900 px-3">
      <div className="flex items-center gap-2">
        <Dropdown label="Select project" trigger={<span className="truncate"><span className="label mr-1.5">Project</span>{project?.name ?? 'None'}</span>}>
          {(close) => projects.length ? projects.map((p) => (
            <Option key={p.id} active={p.id === activeProjectId} onClick={() => { setActiveProject(p.id); close() }}>
              <span className="min-w-0 flex-1 truncate">{p.name}</span>{p.is_demo && <DemoBadge />}
            </Option>
          )) : <div className="px-3 py-2 text-xs text-slate-500">No projects</div>}
        </Dropdown>
        <Dropdown label="Select analysis" width="w-80" trigger={<span className="truncate"><span className="label mr-1.5">Analysis</span>{analysis?.name ?? 'None selected'}</span>}>
          {(close) => projectAnalyses.length ? projectAnalyses.map((a) => (
            <Option key={a.id} active={a.id === analysis?.id} onClick={() => { setActiveAnalysis(a.id); close() }}>
              <span className="min-w-0 flex-1">
                <span className="block truncate">{a.name}</span>
                <span className="font-mono text-2xs text-slate-500">{STATUS_LABEL[a.status]} - {formatDate(a.created_at)}</span>
              </span>
              {a.is_demo && <DemoBadge />}
            </Option>
          )) : <div className="px-3 py-2 text-xs text-slate-500">No analyses yet</div>}
        </Dropdown>
      </div>

      {analysis && (
        <div className="hidden min-w-0 items-center gap-3 text-xs lg:flex">
          <span className="flex items-center gap-1.5 text-slate-400" title="Acquisition dates of the before and after imagery">
            <CalendarRange className="h-3.5 w-3.5 text-slate-500" aria-hidden />
            <span className="font-mono">{formatDate(analysis.before_date)}</span>
            <span className="text-slate-600">&rarr;</span>
            <span className="font-mono">{formatDate(analysis.after_date)}</span>
          </span>
          {analysis.bounds && <span className="hidden font-mono text-2xs text-slate-500 xl:inline" title="Analysed footprint (WGS84)">{analysis.bounds[1].toFixed(3)}, {analysis.bounds[0].toFixed(3)}</span>}
          <span className="flex items-center gap-2">
            <Chip tone={analysis.status === 'failed' ? 'danger' : analysis.status === 'completed' ? 'ok' : 'accent'}>{STATUS_LABEL[analysis.status]}</Chip>
            {running && <span className="w-24"><ProgressBar value={analysis.progress} /></span>}
          </span>
          {analysis.is_demo ? <DemoBadge /> : <Chip tone="ok" title="Computed from real imagery you uploaded or retrieved">Live data</Chip>}
        </div>
      )}

      <div className="flex-1" />

      <div ref={searchRef} className="relative hidden md:block">
        <form onSubmit={submitSearch} role="search">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" aria-hidden />
          <input value={query} onChange={(e) => { setQuery(e.target.value); setSearchOpen(true) }} onFocus={() => setSearchOpen(true)} aria-label="Search analyses or enter lat, lon"
            placeholder="Search analysis or  lat, lon" className="focus-ring h-7 w-56 rounded-md border border-white/[0.08] bg-black/30 pl-7 pr-2 text-xs text-slate-100 placeholder:text-slate-600" />
        </form>
        {searchOpen && (results.length > 0 || coord) && (
          <div className="panel-solid absolute right-0 top-9 z-50 w-72 rounded-md py-1 shadow-2xl shadow-black/70">
            {coord && <Option onClick={() => { setViewMode('map'); submitSearch({ preventDefault() {} } as React.FormEvent) }}>Go to {coord[1]}, {coord[2]}</Option>}
            {results.map((a) => <Option key={a.id} onClick={() => { setActiveAnalysis(a.id); router.push('/map'); setSearchOpen(false) }}><span className="truncate">{a.name}</span></Option>)}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2" title={systemError ?? (system ? `API v${system.version}, ${system.env}` : '')}>
        <span className={cn('h-1.5 w-1.5 rounded-full', backend.tone === 'ok' ? 'bg-emerald-400' : backend.tone === 'warn' ? 'animate-pulse-dot bg-amber-400' : 'bg-red-500')} aria-hidden />
        <span className="hidden font-mono text-2xs uppercase tracking-wider text-slate-500 xl:inline">{backend.text}</span>
        {backend.tone === 'danger' && <AlertCircle className="h-3.5 w-3.5 text-red-400" aria-label={backend.text} />}
      </div>

      <Dropdown label="User menu" align="right" width="w-60" trigger={<><User className="h-3.5 w-3.5 text-accent" aria-hidden /><span className="hidden max-w-[110px] truncate sm:inline">{user?.name}</span></>}>
        {(close) => (
          <>
            <div className="hairline-b px-3 py-2">
              <div className="text-xs text-slate-100">{user?.name}</div>
              <div className="truncate text-2xs text-slate-500">{user?.email}</div>
              <div className="mt-1 font-mono text-2xs uppercase tracking-wider text-accent">{user ? roleLabel[user.role] : ''}</div>
            </div>
            <Option onClick={() => { close(); router.push('/settings') }}>Settings</Option>
            <Option onClick={() => { close(); api.logout(); signOut() }}><LogOut className="mt-0.5 h-3.5 w-3.5" aria-hidden /> Sign out</Option>
          </>
        )}
      </Dropdown>
    </header>
  )
}

export { Radio, Square }
