'use client'

import dynamic from 'next/dynamic'
import { useEffect } from 'react'
import Link from 'next/link'
import { useFeatureData } from '@/hooks/useFeatureData'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { canWrite } from '@/lib/auth'
import { DemoBadge } from '@/components/ui/kit'
import BottomDrawer from '@/components/panels/BottomDrawer'
import IntelligencePanel from '@/components/panels/IntelligencePanel'
import LayerPanel from '@/components/panels/LayerPanel'
import QuickComparePanel from '@/components/panels/QuickComparePanel'
import WeatherAlertCard from '@/components/panels/WeatherAlertCard'
import { CoordinateBar, ToolRail, ViewSwitcher } from './MapChrome'

// Both renderers touch `window`/WebGL, so they are client-only chunks (Cesium is large: loaded only when needed).
const GlobeView = dynamic(() => import('./GlobeView'), { ssr: false })
const MapCanvas = dynamic(() => import('./MapCanvas'), { ssr: false })
const CompareView = dynamic(() => import('./CompareView'), { ssr: false })

export default function CommandCenter() {
  useFeatureData()
  const mode = useAppStore((s) => s.viewMode)
  const setMode = useAppStore((s) => s.setViewMode)
  const leftPanel = useAppStore((s) => s.leftPanel)
  const rightOpen = useAppStore((s) => s.rightPanelOpen)
  const analysis = useAppStore(selectActiveAnalysis)
  const quick = useAppStore((s) => s.quickCompare)
  const drawMode = useAppStore((s) => s.drawMode)
  const setDrawMode = useAppStore((s) => s.setDrawMode)
  useEffect(() => {
    if (!drawMode) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawMode(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawMode, setDrawMode])
  const user = useAppStore((s) => s.authUser)
  const analysesCount = useAppStore((s) => s.analyses.length)
  const featureStatus = useAppStore((s) => s.featureData.status)
  const featureError = useAppStore((s) => s.featureData.error)
  const fc = useAppStore((s) => s.featureData.fc)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 overflow-hidden bg-ink-950">
          {mode === 'globe' && <GlobeView onSwitch2D={() => setMode('map')} />}
          {mode === 'map' && <MapCanvas />}
          {mode === 'compare' && <CompareView />}

          <ToolRail />
          {leftPanel === 'layers' && <LayerPanel />}
          {leftPanel === 'quick' && <QuickComparePanel />}
          <WeatherAlertCard />
          {drawMode && (
            <div role="status" className="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-md border border-cyan-400/40 bg-ink-900/95 px-3 py-1.5 text-xs text-cyan-100">
              Click and drag on the map to draw a rectangle. <span className="text-slate-400">Esc to cancel.</span>
            </div>
          )}
          <ViewSwitcher />
          <CoordinateBar />

          {analysis?.is_demo && (
            <div className="pointer-events-none absolute right-3 top-3 z-20 flex items-center gap-2 rounded border border-demo/40 bg-ink-900/90 px-2.5 py-1.5">
              <DemoBadge /><span className="text-2xs text-slate-400">Synthetic scene, not satellite imagery</span>
            </div>
          )}
          {!analysis && !quick && (
            <div className="absolute left-1/2 top-[18%] z-10 w-[min(420px,90%)] -translate-x-1/2 rounded-lg border border-[color:var(--line-strong)] bg-ink-900/95 p-5 text-center shadow-2xl">
              <h2 className="text-sm font-medium text-slate-100">{analysesCount === 0 ? 'No analyses yet' : 'No analysis selected'}</h2>
              <p className="mt-1 text-xs text-slate-400">Upload a before/after GeoTIFF pair, or search Sentinel-2 imagery for an area and two dates. Results appear here on the globe and the 2D map.</p>
              {canWrite(user?.role)
                ? <Link href="/analyses/new" className="btn mt-3 border-accent-dim bg-accent-surface text-accent hover:bg-[#1a4430]">Start a new analysis</Link>
                : <p className="mt-3 text-2xs text-slate-500">Your role is read-only; ask an analyst to share a project.</p>}
            </div>
          )}
          {analysis && analysis.status === 'completed' && featureStatus === 'error' && (
            <div role="alert" className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded border border-red-500/30 bg-ink-900/95 px-3 py-1.5 text-xs text-red-300">Could not load detections: {featureError}</div>
          )}
          {analysis && analysis.status === 'completed' && featureStatus === 'ready' && fc?.truncated && (
            <div role="status" className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded border border-amber-400/30 bg-ink-900/95 px-3 py-1.5 text-xs text-amber-200">Showing {fc.returned.toLocaleString('en-US')} of {fc.total.toLocaleString('en-US')} detections on the map; the list and exports contain all of them. Use filters to narrow the map.</div>
          )}
          {analysis && analysis.status !== 'completed' && (
            <div className="pointer-events-none absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded border border-[color:var(--line-strong)] bg-ink-900/95 px-3 py-1.5 text-xs text-slate-300">
              {analysis.status === 'failed' ? 'This analysis failed. See Progress for details.' : `Analysis is ${analysis.status.replace(/_/g, ' ')}...`}
            </div>
          )}
        </div>
        {rightOpen && <IntelligencePanel />}
      </div>
      <BottomDrawer />
    </div>
  )
}
