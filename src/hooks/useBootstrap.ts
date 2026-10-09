'use client'

import { useCallback, useEffect, useRef } from 'react'
import { api, ApiError } from '@/lib/api'
import { isActiveStatus } from '@/lib/format'
import { canWrite } from '@/lib/auth'
import { useAppStore } from '@/store/useAppStore'

/** Loads workspace data once the user is authenticated and keeps active analyses / system status fresh. */
export function useBootstrap() {
  const user = useAppStore((s) => s.authUser)
  const loaded = useRef(false)

  const refresh = useCallback(async () => {
    const st = useAppStore.getState()
    const [sys, projects, analyses, layers, regions] = await Promise.allSettled([
      api.systemStatus(), api.projects.list(), api.analyses.list({ limit: 100 }), api.layers.list(), api.regions.list(),
    ])
    // provider weather alerts (stored; no provider call) feed the map's separate weather layer
    api.weather.list({ status: 'active' }).then((w) => useAppStore.getState().setWeatherAlerts(w.items)).catch(() => undefined)
    if (regions.status === 'fulfilled') st.setRegions(regions.value)
    if (sys.status === 'fulfilled') st.setSystem(sys.value)
    else st.setSystem(null, sys.reason instanceof ApiError ? sys.reason.message : 'Backend unavailable')
    if (projects.status === 'fulfilled') {
      let list = projects.value
      if (list.length === 0 && canWrite(st.authUser?.role)) {
        try { list = [await api.projects.ensureDefault()] } catch { /* surfaced by empty state */ }
      }
      st.setProjects(list)
    }
    if (analyses.status === 'fulfilled') {
      st.setAnalyses(analyses.value)
      const cur = useAppStore.getState().activeAnalysisId
      if (!cur || !analyses.value.some((a) => a.id === cur)) {
        const pick = analyses.value.find((a) => a.status === 'completed') ?? null
        if (pick) useAppStore.getState().setActiveAnalysis(pick.id)
      }
    }
    if (layers.status === 'fulfilled') st.setLayerCatalog(layers.value)
  }, [])

  useEffect(() => {
    if (!user || loaded.current) return
    loaded.current = true
    void refresh()
  }, [user, refresh])

  // truthful backend/system status, refreshed periodically
  useEffect(() => {
    if (!user) return
    const t = setInterval(() => {
      api.systemStatus()
        .then((s) => useAppStore.getState().setSystem(s))
        .catch((e) => useAppStore.getState().setSystem(null, e instanceof ApiError ? e.message : 'Backend unavailable'))
    }, 30_000)
    return () => clearInterval(t)
  }, [user])

  // poll analyses that are still running (no fake progress: values come from the server)
  useEffect(() => {
    if (!user) return
    const t = setInterval(async () => {
      const st = useAppStore.getState()
      const running = st.analyses.filter((a) => isActiveStatus(a.status))
      if (!running.length) return
      await Promise.all(running.map(async (a) => {
        try {
          const next = await api.analyses.get(a.id)
          st.upsertAnalysis(next)
          if (isActiveStatus(a.status) && !isActiveStatus(next.status)) {
            if (next.status === 'completed') {
              // bounds only exist once processing finishes: bring the camera to the result if the user is looking at it
              if (next.bounds && useAppStore.getState().activeAnalysisId === next.id) st.requestFly({ bbox: next.bounds })
              st.toast('success', `Analysis "${next.name}" completed: ${next.summary?.feature_count ?? 0} change polygon(s)`)
              if (!useAppStore.getState().activeAnalysisId) useAppStore.getState().setActiveAnalysis(next.id)
              else if (useAppStore.getState().activeAnalysisId === next.id) useAppStore.getState().bumpFeatures()
            } else if (next.status === 'failed') st.toast('error', `Analysis "${next.name}" failed: ${next.error?.message ?? 'unknown error'}`)
          }
        } catch { /* transient; next tick retries */ }
      }))
    }, 1500)
    return () => clearInterval(t)
  }, [user])

  return { refresh }
}
