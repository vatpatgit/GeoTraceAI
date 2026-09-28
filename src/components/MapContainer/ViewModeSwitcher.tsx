'use client'

import { Globe, Satellite, Map as MapIcon } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import type { ViewMode } from '@/types'

interface ModeOption {
  id: ViewMode
  label: string
  icon: typeof Globe
  description: string
}

const MODES: ModeOption[] = [
  {
    id: 'globe',
    label: '3D Globe',
    icon: Globe,
    description: 'Spherical planetary view with atmosphere and global perspective',
  },
  {
    id: 'satellite',
    label: 'Satellite',
    icon: Satellite,
    description: 'High-resolution orthogonal top-down satellite imagery',
  },
  {
    id: 'map',
    label: 'Map',
    icon: MapIcon,
    description: 'Cartographic vector map with boundaries, roads and labels',
  },
]

export default function ViewModeSwitcher() {
  const { mapView, setViewMode } = useAppStore()
  const currentMode = mapView.viewMode || 'globe'

  return (
    <div
      role="radiogroup"
      aria-label="Map projection and view mode"
      className="inline-flex items-center gap-1 p-1 bg-[#0D1321]/90 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl shadow-black/40"
    >
      {MODES.map((mode) => {
        const Icon = mode.icon
        const isActive = currentMode === mode.id

        return (
          <button
            key={mode.id}
            role="radio"
            aria-checked={isActive}
            aria-label={`${mode.label} mode: ${mode.description}`}
            title={`${mode.label} — ${mode.description}`}
            onClick={() => setViewMode(mode.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-[#33E1FF] ${
              isActive
                ? 'bg-[#33E1FF]/15 text-[#33E1FF] border border-[#33E1FF]/30 shadow-inner'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <Icon
              className={`w-3.5 h-3.5 transition-transform duration-200 ${
                isActive ? 'scale-110 text-[#33E1FF]' : 'text-slate-400'
              }`}
            />
            <span className="hidden sm:inline">{mode.label}</span>
          </button>
        )
      })}
    </div>
  )
}
