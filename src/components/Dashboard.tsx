'use client'

import Header from './Header'
import CollapsibleSidebar from './Layout/CollapsibleSidebar'
import BaseMap from './MapContainer/BaseMap'
import AnalyticsPanel from './AnalyticsPanel'
import TimeSlider from './TimeSlider'
import LayerManager from './LayerManager'
import RegionSelector from './RegionSelector'
import AlertConfigurator from './AlertConfigurator'
import ReportDownloader from './ReportDownloader'
import AuthMock from './AuthMock'
import AlertPanel from './AlertSystem/AlertPanel'
import { useAppStore } from '@/store/useAppStore'
import { motion, AnimatePresence } from 'framer-motion'
import { useEffect } from 'react'
import { fetchRegions } from '@/lib/mockApi'

export default function Dashboard() {
  const { analyticsPanelOpen, setRegions, setRegionsLoading, setRegionsError, regions } = useAppStore()

  useEffect(() => {
    let cancelled = false
    setRegionsLoading(true)
    fetchRegions().then((loadedRegions) => {
      if (!cancelled) setRegions(loadedRegions)
    }).catch(() => {
      if (!cancelled) setRegionsError('Unable to load monitoring regions.')
    }).finally(() => {
      if (!cancelled) setRegionsLoading(false)
    })
    return () => { cancelled = true }
  }, [setRegions, setRegionsError, setRegionsLoading])

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0A0F1C]" id="dashboard-root">
      {/* Left Sidebar */}
      <CollapsibleSidebar />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top Header */}
        <Header />

        {/* Center Content */}
        <div className="flex flex-1 overflow-hidden min-h-0">
          {/* Map Area */}
          <div className="relative flex-1 flex flex-col min-w-0">
            {/* Floating Controls (top left) */}
            <div className="absolute top-4 left-4 z-20 flex flex-col gap-2.5">
              <RegionSelector />
              <LayerManager />
            </div>

            {/* Map */}
            <div className="flex-1 relative min-h-0">
              <BaseMap />
              <AlertPanel />
            </div>

            {/* Bottom Time Slider */}
            <div className="border-t border-white/5 bg-[#0D1321]/90 backdrop-blur-sm flex-shrink-0">
              <TimeSlider />
            </div>
          </div>

          {/* Right Analytics Panel */}
          <AnimatePresence>
            {analyticsPanelOpen && (
              <motion.div
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 360, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: 'easeInOut' }}
                className="hidden lg:block border-l border-white/5 overflow-hidden flex-shrink-0"
              >
                <div className="w-[360px] h-full overflow-y-auto">
                  <AnalyticsPanel />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Modals */}
      <AlertConfigurator />
      <ReportDownloader />
      <AuthMock />
    </div>
  )
}
