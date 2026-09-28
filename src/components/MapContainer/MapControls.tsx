'use client'

import { ZoomIn, ZoomOut, Maximize2, Compass, RotateCcw } from 'lucide-react'

interface MapControlsProps {
  map?: any
  onReset?: () => void
}

export default function MapControls({ map, onReset }: MapControlsProps) {
  const handleZoomIn = () => {
    if (map) map.zoomIn({ duration: 300 })
  }

  const handleZoomOut = () => {
    if (map) map.zoomOut({ duration: 300 })
  }

  const handleResetNorth = () => {
    if (map) {
      map.resetNorthPitch({ duration: 500 })
    }
  }

  const handleFullscreen = () => {
    const root = document.getElementById('dashboard-root') || document.documentElement
    if (!document.fullscreenElement) {
      if (root.requestFullscreen) {
        root.requestFullscreen()
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen()
      }
    }
  }

  return (
    <div
      aria-label="Map navigation controls"
      className="flex flex-col gap-1.5 p-1 bg-[#0D1321]/90 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl shadow-black/50"
    >
      <button
        onClick={handleZoomIn}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
        title="Zoom In"
        aria-label="Zoom in"
      >
        <ZoomIn className="w-4 h-4" />
      </button>

      <button
        onClick={handleZoomOut}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
        title="Zoom Out"
        aria-label="Zoom out"
      >
        <ZoomOut className="w-4 h-4" />
      </button>

      <div className="w-full h-px bg-white/10 my-0.5" />

      <button
        onClick={handleResetNorth}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
        title="Reset North & Pitch"
        aria-label="Reset orientation"
      >
        <Compass className="w-4 h-4" />
      </button>

      {onReset && (
        <button
          onClick={onReset}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
          title="Reset Global View"
          aria-label="Reset global view"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      )}

      <button
        onClick={handleFullscreen}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
        title="Toggle Fullscreen"
        aria-label="Toggle fullscreen"
      >
        <Maximize2 className="w-4 h-4" />
      </button>
    </div>
  )
}
