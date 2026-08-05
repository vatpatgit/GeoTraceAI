'use client'

import { MapPin, ChevronDown, Globe } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { REGIONS, getRegionSummary } from '@/lib/mockData'
import { motion, AnimatePresence } from 'framer-motion'

export default function RegionSelector() {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const { selectedRegion, setSelectedRegion } = useAppStore()

  const selectedData = REGIONS.find((r) => r.id === selectedRegion)

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div ref={dropdownRef} className="relative z-30">
      {/* Trigger */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-3 px-4 py-2.5 glass-card rounded-xl hover:border-accent/30 transition-all group w-full min-w-[280px]"
        aria-label="Select region"
        aria-expanded={isOpen}
        id="region-selector-trigger"
      >
        <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center flex-shrink-0 group-hover:bg-accent/25 transition-colors">
          <Globe className="w-4 h-4 text-accent" />
        </div>
        <div className="flex-1 text-left min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
            Monitoring Region
          </div>
          <div className="text-sm font-medium text-white truncate">
            {selectedData?.name || 'Select region...'}
          </div>
        </div>
        <ChevronDown
          className={`w-4 h-4 text-slate-400 transition-transform duration-200 flex-shrink-0 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="absolute top-full left-0 right-0 mt-2 glass-card rounded-xl shadow-2xl overflow-hidden"
            style={{ minWidth: '320px' }}
          >
            <div className="p-2 max-h-[360px] overflow-y-auto">
              {REGIONS.map((region) => {
                const summary = getRegionSummary(region.id)
                const isSelected = selectedRegion === region.id

                return (
                  <button
                    key={region.id}
                    onClick={() => {
                      setSelectedRegion(region.id)
                      setIsOpen(false)
                    }}
                    className={`w-full flex items-start gap-3 px-3 py-3 rounded-lg text-left transition-all ${
                      isSelected
                        ? 'bg-accent/10 border border-accent/20'
                        : 'hover:bg-white/5 border border-transparent'
                    }`}
                    id={`region-option-${region.id}`}
                  >
                    <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                      isSelected ? 'bg-accent shadow-sm shadow-accent/50' : 'bg-slate-500'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className={`text-sm font-medium truncate ${
                        isSelected ? 'text-accent' : 'text-white'
                      }`}>
                        {region.name}
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-[11px] text-slate-400">
                          {(region.areaKm2 / 1000).toFixed(0)}K km²
                        </span>
                        {summary && (
                          <>
                            <span className="text-[11px] text-slate-500">•</span>
                            <span className="text-[11px] text-slate-400">
                              {summary.totalAlerts} alerts
                            </span>
                            <span className="text-[11px] text-slate-500">•</span>
                            <span className={`text-[11px] ${
                              summary.trend === 'increasing' ? 'text-red-400' : 'text-green-400'
                            }`}>
                              {summary.trend === 'increasing' ? '↑' : '↓'} {summary.trend}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
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
