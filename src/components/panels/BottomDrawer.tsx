'use client'

import { useRef } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { cn, formatDate, isActiveStatus } from '@/lib/format'
import { selectActiveAnalysis, useAppStore, type DrawerTab } from '@/store/useAppStore'
import { IconButton } from '@/components/ui/kit'
import DetectionList from './DetectionList'
import DownloadsView from './DownloadsView'
import JobProgress from './JobProgress'
import StatsView from './StatsView'

const TABS: { id: DrawerTab; label: string }[] = [
  { id: 'detections', label: 'Detections' }, { id: 'progress', label: 'Progress' }, { id: 'stats', label: 'Statistics' }, { id: 'downloads', label: 'Downloads' },
]

/** Before/after acquisition timeline: honest about unknown dates, shows the real interval. */
function Timeline() {
  const a = useAppStore(selectActiveAnalysis)
  if (!a) return null
  const days = a.before_date && a.after_date ? Math.round((new Date(a.after_date).getTime() - new Date(a.before_date).getTime()) / 86400000) : null
  return (
    <div className="hidden items-center gap-2 font-mono text-2xs text-slate-500 md:flex" aria-label="Acquisition timeline">
      <span className="text-slate-300">{formatDate(a.before_date)}</span>
      <span className="relative h-px w-24 bg-slate-600"><span className="absolute -left-0.5 -top-[3px] h-[7px] w-[7px] rounded-full border border-slate-400 bg-ink-900" /><span className="absolute -right-0.5 -top-[3px] h-[7px] w-[7px] rounded-full bg-accent" /></span>
      <span className="text-accent">{formatDate(a.after_date)}</span>
      <span>{days !== null ? `${days} d` : 'dates unknown'}</span>
    </div>
  )
}

export default function BottomDrawer() {
  const open = useAppStore((s) => s.drawerOpen)
  const setOpen = useAppStore((s) => s.setDrawerOpen)
  const height = useAppStore((s) => s.drawerHeight)
  const setHeight = useAppStore((s) => s.setDrawerHeight)
  const tab = useAppStore((s) => s.drawerTab)
  const setTab = useAppStore((s) => s.setDrawerTab)
  const analysis = useAppStore(selectActiveAnalysis)
  const drag = useRef<{ y: number; h: number } | null>(null)
  const running = analysis && isActiveStatus(analysis.status)

  return (
    <section aria-label="Analysis drawer" className="panel relative z-10 flex shrink-0 flex-col border-x-0 border-b-0" style={{ height: open ? height : 36 }}>
      {open && (
        <div
          role="separator" aria-orientation="horizontal" aria-label="Resize drawer" tabIndex={0}
          onPointerDown={(e) => { drag.current = { y: e.clientY, h: height }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) }}
          onPointerMove={(e) => { if (drag.current) setHeight(drag.current.h + (drag.current.y - e.clientY)) }}
          onPointerUp={() => { drag.current = null }}
          onKeyDown={(e) => { if (e.key === 'ArrowUp') setHeight(height + 24); if (e.key === 'ArrowDown') setHeight(height - 24) }}
          className="focus-ring absolute -top-1 left-0 right-0 z-20 h-2 cursor-row-resize"
        />
      )}
      <div className="hairline-b flex h-9 shrink-0 items-center gap-1 px-2" role="tablist" aria-label="Drawer sections">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id && open} onClick={() => setTab(t.id)} className={cn('focus-ring relative rounded px-2.5 py-1 text-xs transition-colors', tab === t.id && open ? 'text-accent' : 'text-slate-400 hover:text-slate-100')}>
            {t.label}
            {t.id === 'progress' && running && <span className="ml-1.5 inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" aria-label="running" />}
            {tab === t.id && open && <span className="absolute inset-x-2 -bottom-[5px] h-[2px] rounded-full bg-accent" />}
          </button>
        ))}
        <div className="flex-1" />
        <Timeline />
        <IconButton label={open ? 'Collapse drawer' : 'Expand drawer'} onClick={() => setOpen(!open)}>{open ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}</IconButton>
      </div>
      {open && (
        <div className="min-h-0 flex-1" role="tabpanel">
          {tab === 'detections' && <DetectionList />}
          {tab === 'progress' && <JobProgress />}
          {tab === 'stats' && <StatsView />}
          {tab === 'downloads' && <DownloadsView />}
        </div>
      )}
    </section>
  )
}
