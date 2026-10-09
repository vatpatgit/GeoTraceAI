'use client'

import { BoxSelect, Box, CalendarRange, Columns2, Crosshair, Layers, Map as MapIcon, PanelBottom, PanelRight } from 'lucide-react'
import { formatCoord } from '@/lib/format'
import { selectActiveAnalysis, useAppStore, type ViewMode } from '@/store/useAppStore'
import { useCursorStore } from '@/store/useCursorStore'
import { IconButton, Segmented } from '@/components/ui/kit'

/** Bottom-left 3D / 2D / Compare switcher. Camera is carried across views through the shared store. */
export function ViewSwitcher() {
  const mode = useAppStore((s) => s.viewMode)
  const setMode = useAppStore((s) => s.setViewMode)
  const analysis = useAppStore(selectActiveAnalysis)
  const quick = useAppStore((s) => s.quickCompare)
  const canCompare = analysis?.status === 'completed' || !!quick
  return (
    <div className="panel absolute bottom-9 left-3 z-20 rounded-md p-1">
      <Segmented<ViewMode>
        label="View mode"
        value={mode}
        onChange={setMode}
        options={[
          { value: 'globe', label: <span className="inline-flex items-center gap-1"><Box className="h-3 w-3" aria-hidden />3D</span>, title: '3D globe (CesiumJS)' },
          { value: 'map', label: <span className="inline-flex items-center gap-1"><MapIcon className="h-3 w-3" aria-hidden />2D</span>, title: '2D map (MapLibre)' },
          { value: 'compare', label: <span className="inline-flex items-center gap-1"><Columns2 className="h-3 w-3" aria-hidden />Compare</span>, title: canCompare ? 'Before / after slider' : 'Needs a completed analysis or retrieved dates', disabled: !canCompare },
        ]}
      />
    </div>
  )
}

/** Floating right tool rail: layers, fit, panel toggles. Every button has a label + tooltip. */
export function ToolRail() {
  const leftPanel = useAppStore((s) => s.leftPanel)
  const setLeftPanel = useAppStore((s) => s.setLeftPanel)
  const rightOpen = useAppStore((s) => s.rightPanelOpen)
  const setRightOpen = useAppStore((s) => s.setRightPanelOpen)
  const drawerOpen = useAppStore((s) => s.drawerOpen)
  const setDrawerOpen = useAppStore((s) => s.setDrawerOpen)
  const requestFly = useAppStore((s) => s.requestFly)
  const analysis = useAppStore(selectActiveAnalysis)
  const drawMode = useAppStore((s) => s.drawMode)
  const setDrawMode = useAppStore((s) => s.setDrawMode)
  const viewMode = useAppStore((s) => s.viewMode)
  const setViewMode = useAppStore((s) => s.setViewMode)
  const startDraw = () => {
    if (drawMode) { setDrawMode(false); return }
    if (viewMode === 'compare') setViewMode('globe') // drawing needs a single map or the globe
    setLeftPanel('quick')
    setDrawMode(true)
  }
  return (
    <div className="panel absolute left-3 top-3 z-20 flex flex-col gap-0.5 rounded-md p-1" role="toolbar" aria-label="Map tools" aria-orientation="vertical">
      <IconButton label="Layers" active={leftPanel === 'layers'} onClick={() => setLeftPanel(leftPanel === 'layers' ? null : 'layers')}><Layers className="h-4 w-4" /></IconButton>
      <IconButton label="Select an area: drag a rectangle on the map" active={drawMode} onClick={startDraw}><BoxSelect className="h-4 w-4" /></IconButton>
      <IconButton label="Compare two dates (Sentinel-2)" active={leftPanel === 'quick'} onClick={() => setLeftPanel(leftPanel === 'quick' ? null : 'quick')}><CalendarRange className="h-4 w-4" /></IconButton>
      <IconButton label="Fit to analysis area" disabled={!analysis?.bounds} onClick={() => analysis?.bounds && requestFly({ bbox: analysis.bounds })}><Crosshair className="h-4 w-4" /></IconButton>
      <div className="my-0.5 h-px bg-white/[0.07]" />
      <IconButton label={rightOpen ? 'Hide intelligence panel' : 'Show intelligence panel'} active={rightOpen} onClick={() => setRightOpen(!rightOpen)}><PanelRight className="h-4 w-4" /></IconButton>
      <IconButton label={drawerOpen ? 'Hide analysis drawer' : 'Show analysis drawer'} active={drawerOpen} onClick={() => setDrawerOpen(!drawerOpen)}><PanelBottom className="h-4 w-4" /></IconButton>
    </div>
  )
}

/** Bottom status line: cursor coordinates, zoom, scale, data provenance. */
export function CoordinateBar() {
  const { lon, lat, zoom, scaleLabel } = useCursorStore()
  const viewMode = useAppStore((s) => s.viewMode)
  const analysis = useAppStore(selectActiveAnalysis)
  return (
    <div className="hairline-t absolute bottom-0 left-0 right-0 z-20 flex h-7 items-center gap-4 bg-ink-900/90 px-3 font-mono text-2xs text-slate-500 backdrop-blur">
      <span aria-label="Cursor position">{lon !== null && lat !== null ? formatCoord(lon, lat) : 'cursor: -'}</span>
      <span>zoom {zoom !== null ? zoom.toFixed(1) : '-'}</span>
      {scaleLabel && viewMode !== 'globe' && <span className="flex items-center gap-1.5"><span className="inline-block h-[3px] w-[100px] border-x border-b border-slate-500" aria-hidden />{scaleLabel}</span>}
      <span className="flex-1" />
      <span>WGS84 / EPSG:4326</span>
      {analysis && <span className="hidden md:inline">grid {analysis.processing?.grid ? `${analysis.processing.grid.pixel_size_m} m EPSG:${analysis.processing.grid.crs_epsg}` : '-'}</span>}
    </div>
  )
}
