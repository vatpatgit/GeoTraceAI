'use client'

import { useEffect } from 'react'
import { api, ApiError } from '@/lib/api'
import { toFeatureFilters, useAppStore } from '@/store/useAppStore'

/**
 * Single source of truth for the polygons drawn by the globe, the 2D map and the compare view.
 * Filtering is server-side (same query as the list and the exports) so what you see is what you export.
 */
export function useFeatureData() {
  const analysisId = useAppStore((s) => s.activeAnalysisId)
  const status = useAppStore((s) => s.analyses.find((a) => a.id === s.activeAnalysisId)?.status)
  const filters = useAppStore((s) => s.filters)
  const version = useAppStore((s) => s.featuresVersion)
  const setFeatureData = useAppStore((s) => s.setFeatureData)

  useEffect(() => {
    if (!analysisId || status !== 'completed') {
      setFeatureData({ analysisId, status: 'idle', error: null, fc: null })
      return
    }
    const ctrl = new AbortController()
    setFeatureData({ analysisId, status: 'loading', error: null })
    const t = setTimeout(() => {
      api.analyses.featuresGeoJSON(analysisId, toFeatureFilters(filters), 5000, ctrl.signal)
        .then((fc) => setFeatureData({ analysisId, status: 'ready', error: null, fc }))
        .catch((e) => {
          if ((e as Error).name === 'AbortError') return
          setFeatureData({ analysisId, status: 'error', error: e instanceof ApiError ? e.message : 'Failed to load detections', fc: null })
        })
    }, 120)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [analysisId, status, filters, version, setFeatureData])
}
