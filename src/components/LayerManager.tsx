'use client'

import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Layers, Eye, EyeOff, Lock, ChevronDown, ChevronRight,
  Satellite, Map, Type, AlertTriangle, Leaf, Thermometer,
  CloudRain, Droplets, Wind, Flame, Waves, TreePine,
} from 'lucide-react'
import type { LayerDefinition, LayerCategory } from '@/types/layers'
import { LAYER_REGISTRY, getLayersByCategory } from '@/services/maps/layerRegistry'
import { LAYER_CATEGORIES } from '@/services/maps/layerTypes'
import { useAppStore } from '@/store/useAppStore'

const ICON_MAP: Record<string, any> = {
  Satellite, Map, Type, AlertTriangle, Leaf, Thermometer,
  CloudRain, Droplets, Wind, Flame, Waves, TreePine,
}

// Category color mapping
const CATEGORY_COLORS: Record<string, string> = {
  base: '#3B82F6',
  monitoring: '#10B981',
  environmental: '#F59E0B',
  risk: '#EF4444',
}

export default function LayerManager() {
  const [isExpanded, setIsExpanded] = useState(false)

  // Start with all categories expanded by default or just some
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(['base', 'monitoring', 'environmental', 'risk'])
  )

  const layerVisibility = useAppStore(state => state.layerVisibility)
  const setLayerVisibility = useAppStore(state => state.setLayerVisibility)
  const setLayerOpacity = useAppStore(state => state.setLayerOpacity)

  // Toggle category expansion
  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev)
      if (next.has(categoryId)) next.delete(categoryId)
      else next.add(categoryId)
      return next
    })
  }

  // Count active layers for the collapsed dot indicators
  const activeCount = Object.keys(layerVisibility).filter(
    id => layerVisibility[id]?.visible
  ).length

  return (
    <div className="glass-card bg-[#0D1321]/95 backdrop-blur border border-white/[0.06] rounded-xl overflow-hidden shadow-2xl flex flex-col pointer-events-auto" style={{ minWidth: '240px' }}>
      {/* Collapsed header button */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center justify-between p-3 w-full hover:bg-white/[0.04] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Layers size={18} className="text-slate-300" />
          <span className="text-sm font-medium text-slate-200">Map Layers</span>
        </div>

        <div className="flex items-center gap-2">
          {!isExpanded && activeCount > 0 && (
            <div className="flex gap-1.5 items-center bg-[#33E1FF]/10 px-2 py-0.5 rounded-full border border-[#33E1FF]/20">
              <span className="w-1.5 h-1.5 rounded-full bg-[#33E1FF]" />
              <span className="text-xs font-medium text-[#33E1FF]">{activeCount}</span>
            </div>
          )}
          {isExpanded ? <ChevronDown size={16} className="text-slate-500" /> : <ChevronRight size={16} className="text-slate-500" />}
        </div>
      </button>

      {/* Expanded Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-white/[0.06]"
          >
            <div className="p-2 space-y-2 max-h-[60vh] overflow-y-auto custom-scrollbar">
              {LAYER_CATEGORIES.map(category => {
                // Handle category if it's string or object
                const catId = typeof category === 'string' ? category : (category as any).id;
                const catLabel = typeof category === 'string' ? category : (category as any).label || (category as any).name || (category as any).id;

                const allGrouped = getLayersByCategory()
                const layers = allGrouped[catId as keyof typeof allGrouped]
                if (!layers || layers.length === 0) return null

                const isCatExpanded = expandedCategories.has(catId)
                const color = CATEGORY_COLORS[catId] || '#33E1FF'

                return (
                  <div key={catId} className="flex flex-col">
                    <button
                      onClick={() => toggleCategory(catId)}
                      className="flex items-center justify-between p-2 rounded-lg hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{catLabel}</span>
                      </div>
                      {isCatExpanded ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />}
                    </button>

                    <AnimatePresence>
                      {isCatExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden ml-2"
                        >
                          <div className="flex flex-col gap-1 py-1">
                            {layers.map(layer => {
                              const isVisible = layerVisibility[layer.id]?.visible ?? false;
                              const opacity = Math.round((layerVisibility[layer.id]?.opacity ?? 1) * 100);

                              // Use the mapped icon or fallback
                              const Icon = ICON_MAP[layer.icon || 'Map'] || Map;

                              // Determine if layer is disabled placeholder
                              const isDisabled = (layer as any).disabled || (layer as any).status === 'coming_soon';

                              return (
                                <div key={layer.id} className="flex flex-col">
                                  <div
                                    className={`flex items-center justify-between p-2 rounded-lg transition-colors
                                      ${isDisabled ? 'opacity-50 grayscale cursor-not-allowed' : 'hover:bg-white/[0.04]'}`}
                                  >
                                    <div className="flex items-center gap-3">
                                      <Icon size={16} className={isVisible && !isDisabled ? 'text-white' : 'text-slate-500'} style={{ color: isVisible && !isDisabled ? color : undefined }} />
                                      <span className="text-sm text-slate-300">{layer.name}</span>
                                    </div>

                                    {isDisabled ? (
                                      <div className="flex items-center gap-2">
                                        <span className="text-[10px] uppercase font-bold text-slate-500 bg-slate-800/80 px-1.5 py-0.5 rounded border border-white/[0.05]">Soon</span>
                                        <Lock size={14} className="text-slate-600" />
                                      </div>
                                    ) : (
                                      <button
                                        onClick={() => setLayerVisibility(layer.id, !isVisible)}
                                        className="text-slate-400 hover:text-white transition-colors p-1 -m-1"
                                      >
                                        {isVisible ? <Eye size={16} style={{ color }} /> : <EyeOff size={16} />}
                                      </button>
                                    )}
                                  </div>

                                  {/* Opacity Slider */}
                                  <AnimatePresence>
                                    {isVisible && !isDisabled && (
                                      <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: 'auto', opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        className="px-8 pb-2 overflow-hidden"
                                      >
                                        <div className="flex items-center gap-2 mt-1">
                                          <span className="text-[10px] text-slate-500 w-8">{opacity}%</span>
                                          <input
                                            type="range"
                                            min="0"
                                            max="100"
                                            value={opacity}
                                            onChange={(e) => setLayerOpacity(layer.id, parseInt(e.target.value) / 100)}
                                            className="flex-1 h-1 bg-slate-700/50 rounded-lg appearance-none cursor-pointer"
                                            style={{ accentColor: color }}
                                          />
                                        </div>
                                      </motion.div>
                                    )}
                                  </AnimatePresence>
                                </div>
                              )
                            })}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
