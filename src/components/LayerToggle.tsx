'use client'

import { Satellite, Eye, EyeOff, Activity, Layers } from 'lucide-react'
import { useState } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { motion, AnimatePresence } from 'framer-motion'

export default function LayerToggle() {
  const { mapView, toggleLayer } = useAppStore()
  const [isExpanded, setIsExpanded] = useState(false)

  const layers = [
    {
      id: 'satellite' as const,
      label: 'Satellite',
      icon: Satellite,
      color: '#3B82F6',
    },
    {
      id: 'changeMask' as const,
      label: 'Change Detection',
      icon: Activity,
      color: '#EF4444',
    },
    {
      id: 'confidence' as const,
      label: 'Confidence',
      icon: Activity,
      color: '#33E1FF',
    },
  ]

  return (
    <div className="glass-card rounded-xl overflow-hidden" style={{ minWidth: '200px' }}>
      {/* Collapsed header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-white/[0.03] transition-colors"
        id="layers-toggle-btn"
      >
        <div className="w-6 h-6 rounded-md bg-white/5 flex items-center justify-center">
          <Layers className="w-3.5 h-3.5 text-accent" />
        </div>
        <span className="text-xs font-semibold text-slate-300 flex-1 text-left">Map Layers</span>
        <div className="flex gap-1">
          {layers.map((l) => (
            <div
              key={l.id}
              className={`w-1.5 h-1.5 rounded-full transition-colors ${
                mapView.activeLayers[l.id] ? '' : 'opacity-30'
              }`}
              style={{ background: l.color }}
            />
          ))}
        </div>
      </button>

      {/* Expanded layers */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="px-2 pb-2 space-y-1 border-t border-white/[0.04] pt-1.5">
              {layers.map((layer) => {
                const Icon = layer.icon
                const isActive = mapView.activeLayers[layer.id]

                return (
                  <button
                    key={layer.id}
                    onClick={() => toggleLayer(layer.id)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-all ${
                      isActive
                        ? 'bg-white/[0.06]'
                        : 'hover:bg-white/[0.03] opacity-60'
                    }`}
                    aria-label={`Toggle ${layer.label} layer`}
                    id={`layer-${layer.id}`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className="w-3.5 h-3.5" style={{ color: isActive ? layer.color : '#6B7280' }} />
                      <span className="text-xs font-medium text-slate-300">{layer.label}</span>
                    </div>
                    {isActive ? (
                      <Eye className="w-3.5 h-3.5 text-slate-400" />
                    ) : (
                      <EyeOff className="w-3.5 h-3.5 text-slate-600" />
                    )}
                  </button>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
