'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { Map as MlMap, MapMouseEvent } from 'maplibre-gl'
import { AlertTriangle } from 'lucide-react'
import { loadMapLibrary } from '@/services/maps/mapProvider'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { useCursorStore } from '@/store/useCursorStore'
import { baseStyle, DARK_LAYER, SATELLITE_LAYER } from './basemaps'
import { type MapRole, syncLayers, transformRequest } from './maplibreLayers'
import { layerTileUrl } from '@/lib/layers/env'
import { syncQuickChanges, syncQuickImage } from './quickImage'
import { syncWeather, WEATHER_FILL } from './weatherLayer'
import { boxFromCorners, syncDrawBox } from './drawBox'

interface Props {
  role?: MapRole
  /** false => pointer events pass through (the top map in compare mode owns interaction) */
  interactive?: boolean
  onMap?: (map: MlMap | null) => void
  className?: string
}

/** One MapLibre instance wired to the shared store. Used alone (2D) and twice (compare). */
export default function MapCanvas({ role = 'single', interactive = true, onMap, className }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const analysis = useAppStore(selectActiveAnalysis)
  const layerState = useAppStore((s) => s.layerState)
  const catalog = useAppStore((s) => s.layerCatalog)
  const fc = useAppStore((s) => s.featureData.fc)
  const regions = useAppStore((s) => s.regions)
  const selectedId = useAppStore((s) => s.selectedFeatureId)
  const hoveredId = useAppStore((s) => s.hoveredFeatureId)
  const basemap = useAppStore((s) => s.basemap)
  const flyRequest = useAppStore((s) => s.flyRequest)
  const quickCompare = useAppStore((s) => s.quickCompare)
  const quickChanges = useAppStore((s) => s.quickChanges)
  const weatherAlerts = useAppStore((s) => s.weatherAlerts)
  const drawMode = useAppStore((s) => s.drawMode)
  const drawnBox = useAppStore((s) => s.drawnBox)
  const selectedWeatherId = useAppStore((s) => s.selectedWeatherId)
  const falseColor = false

  const ctx = useMemo(() => ({
    role, analysisId: analysis?.id ?? null, completed: analysis?.status === 'completed', bounds: analysis?.bounds ?? null,
    hasNdvi: !!analysis?.processing?.grid?.roles?.includes('nir') && !!analysis?.processing?.grid?.roles?.includes('red'),
    falseColor, layerState, catalog, fc, regions, selectedId, hoveredId, envTileUrl: (l: import('@/lib/api').LayerInfo) => layerTileUrl(l, analysis, 'maplibre'),
  }), [role, analysis, layerState, catalog, fc, regions, selectedId, hoveredId, falseColor])
  const ctxRef = useRef(ctx)
  ctxRef.current = ctx
  const refitRef = useRef<{ bbox: [number, number, number, number]; userMoved: boolean } | null>(null)
  const fitTo = (map: MlMap, bbox: [number, number, number, number], duration: number) => {
    const el = container.current
    const pw = Math.min(60, (el?.clientWidth ?? 600) * 0.1); const ph = Math.min(60, (el?.clientHeight ?? 400) * 0.1)
    map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: { top: ph, bottom: ph, left: pw, right: pw }, maxZoom: 17, duration })
  }

  // ---- create the map once ------------------------------------------------------------------------------------
  useEffect(() => {
    if (!container.current) return
    let cancelled = false
    let map: MlMap | null = null
    ;(async () => {
      try {
        const lib = await loadMapLibrary()
        if (cancelled || !container.current) return
        const st = useAppStore.getState()
        map = new lib.Map({
          container: container.current,
          style: baseStyle(st.basemap),
          center: st.camera.center,
          zoom: Math.max(st.camera.zoom, 1),
          bearing: st.camera.bearing,
          pitch: 0,
          attributionControl: role === 'after' || role === 'single' ? { compact: true } : false,
          transformRequest,
          maxZoom: 21,
          fadeDuration: 0,
          interactive,
        }) as MlMap
        mapRef.current = map
        if (process.env.NODE_ENV !== 'production') (window as unknown as Record<string, unknown>)[`__gtMap_${role}`] = map
        // the container's size settles after first paint (panels, drawer); keep the GL canvas in step with it
        let roFrame = 0
        const ro = new ResizeObserver(() => {
          cancelAnimationFrame(roFrame)
          roFrame = requestAnimationFrame(() => {
            if (!map) return
            map.resize()
            const r = refitRef.current
            if (r && !r.userMoved) fitTo(map, r.bbox, 0)
            map.triggerRepaint()
          })
        })
        ro.observe(container.current)
        ;(map as unknown as { __ro: ResizeObserver }).__ro = ro
        map.on('load', () => {
          if (cancelled) return
          map!.resize()
          syncLayers(map!, ctxRef.current)
          setReady(true)
          onMap?.(map)
        })
        map.on('error', (e) => {
          const msg = (e as { error?: { message?: string } }).error?.message ?? ''
          if (process.env.NODE_ENV !== 'production') console.warn('[maplibre error]', msg)
          if (/Failed to fetch|NetworkError|403|401|Unauthorized/i.test(msg)) setError('Some map tiles could not be loaded (network or permission).')
        })
        if (interactive) {
          let raf = 0
          map.on('mousemove', (e: MapMouseEvent) => {
            if (raf) return
            raf = requestAnimationFrame(() => { raf = 0; useCursorStore.getState().set({ lon: e.lngLat.lng, lat: e.lngLat.lat }) })
          })
          map.on('move', () => {
            const z = map!.getZoom()
            const lat = map!.getCenter().lat
            const mpp = (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** z
            const target = mpp * 100
            const nice = [1, 2, 5].flatMap((m) => [10, 100, 1000, 10000, 100000].map((p) => (m * p) / 10)).sort((a, b) => a - b).filter((v) => v <= target).pop() ?? 1
            useCursorStore.getState().set({ zoom: z, scaleLabel: nice >= 1000 ? `${nice / 1000} km` : `${nice} m` })
          })
          map.on('moveend', (e) => {
            if (!(e as { originalEvent?: unknown }).originalEvent) return // programmatic moves are already in the store
            if (refitRef.current) refitRef.current.userMoved = true
            const c = map!.getCenter()
            useAppStore.getState().setCamera({ center: [c.lng, c.lat], zoom: map!.getZoom(), bearing: map!.getBearing(), pitch: map!.getPitch() })
          })
          if (role !== 'before') {
            map.on('click', (e: MapMouseEvent) => {
              const hits = map!.queryRenderedFeatures(e.point, { layers: ['features-fill'] })
              const id = hits[0]?.properties?.id as string | undefined
              if (id) { useAppStore.getState().selectWeather(null); useAppStore.getState().selectFeature(id); return }
              const wx = map!.getLayer(WEATHER_FILL) ? map!.queryRenderedFeatures(e.point, { layers: [WEATHER_FILL, 'weather-alerts-point'] }) : []
              const wid = wx[0]?.properties?.id as string | undefined
              if (wid) { useAppStore.getState().selectFeature(null); useAppStore.getState().selectWeather(wid); return }
              useAppStore.getState().selectFeature(null)
              useAppStore.getState().selectWeather(null)
            })
            map.on('mousemove', 'features-fill', (e) => {
              map!.getCanvas().style.cursor = 'pointer'
              const id = e.features?.[0]?.properties?.id as string | undefined
              if (id && id !== useAppStore.getState().hoveredFeatureId) useAppStore.getState().setHoveredFeature(id)
            })
            map.on('mouseleave', 'features-fill', () => {
              map!.getCanvas().style.cursor = ''
              useAppStore.getState().setHoveredFeature(null)
            })
          }
        }
      } catch (e) {
        if (!cancelled) setError(`The 2D map could not start: ${(e as Error).message}`)
      }
    })()
    return () => {
      cancelled = true
      setReady(false)
      onMap?.(null)
      ;(map as unknown as { __ro?: ResizeObserver } | null)?.__ro?.disconnect()
      map?.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- reconcile overlays with shared state -------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    syncLayers(map, ctx)
  }, [ctx, ready])

  // ---- on-demand Sentinel-2 images (compare-by-date tool) -----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    syncQuickImage(map, quickCompare, role)
    syncQuickChanges(map, quickChanges.data, quickChanges.show && !!quickCompare, role)
  }, [quickCompare, quickChanges, role, ready, ctx])

  // ---- select an area by dragging a rectangle (single 2D map only) -----------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || role !== 'single') return
    syncDrawBox(map, drawnBox)
  }, [drawnBox, role, ready, ctx])
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || role !== 'single' || !drawMode) return
    const canvas = map.getCanvas()
    map.dragPan.disable(); map.boxZoom.disable(); map.doubleClickZoom.disable()
    canvas.style.cursor = 'crosshair'
    let start: [number, number] | null = null
    const down = (e: MapMouseEvent) => { start = [e.lngLat.lng, e.lngLat.lat]; e.preventDefault() }
    const move = (e: MapMouseEvent) => { if (start) syncDrawBox(map, boxFromCorners(start, [e.lngLat.lng, e.lngLat.lat])) }
    const up = (e: MapMouseEvent) => {
      if (!start) return
      const s0 = start; start = null
      const end: [number, number] = [e.lngLat.lng, e.lngLat.lat]
      if (Math.abs(end[0] - s0[0]) > 1e-5 && Math.abs(end[1] - s0[1]) > 1e-5) {
        const b = boxFromCorners(s0, end)
        useAppStore.getState().setDrawnBox([+b[0].toFixed(5), +b[1].toFixed(5), +b[2].toFixed(5), +b[3].toFixed(5)])
        useAppStore.getState().setDrawMode(false)
      } else syncDrawBox(map, useAppStore.getState().drawnBox)
    }
    map.on('mousedown', down); map.on('mousemove', move); map.on('mouseup', up)
    return () => {
      map.off('mousedown', down); map.off('mousemove', move); map.off('mouseup', up)
      map.dragPan.enable(); map.boxZoom.enable(); map.doubleClickZoom.enable()
      canvas.style.cursor = ''
      syncDrawBox(map, useAppStore.getState().drawnBox)
    }
  }, [drawMode, role, ready])

  // ---- provider weather alerts (own layer group; never mixed with imagery / change polygons) -------------------
  const wxLayer = useAppStore((s) => s.layerState['weather-alerts'])
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || role === 'before') return
    syncWeather(map, weatherAlerts, wxLayer?.visible ?? true, wxLayer?.opacity ?? 0.45, selectedWeatherId)
  }, [weatherAlerts, selectedWeatherId, wxLayer, role, ready, ctx])

  // ---- basemap toggle -----------------------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setLayoutProperty(SATELLITE_LAYER, 'visibility', basemap === 'satellite' ? 'visible' : 'none')
    map.setLayoutProperty(DARK_LAYER, 'visibility', basemap === 'dark' ? 'visible' : 'none')
  }, [basemap, ready])

  // ---- camera requests (fit analysis / fly to detection) ------------------------------------------------------
  const lastFly = useRef(0)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !flyRequest || flyRequest.id === lastFly.current) return
    lastFly.current = flyRequest.id
    const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const duration = reduce ? 0 : 900
    if (flyRequest.bbox) {
      refitRef.current = { bbox: flyRequest.bbox, userMoved: false }
      fitTo(map, flyRequest.bbox, duration)
    } else if (flyRequest.center) {
      map.flyTo({ center: flyRequest.center, zoom: flyRequest.zoom ?? Math.max(map.getZoom(), 14), duration })
    }
    const done = () => {
      const c = map.getCenter()
      useAppStore.getState().setCamera({ center: [c.lng, c.lat], zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() })
    }
    map.once('moveend', done)
  }, [flyRequest, ready])

  return (
    <div className={className ?? 'absolute inset-0'} style={interactive ? undefined : { pointerEvents: 'none' }}>
      <div ref={container} className="h-full w-full" role="application" aria-label={role === 'before' ? 'Before imagery map' : role === 'after' ? 'After imagery map' : '2D map'} />
      {error && (
        <div role="alert" className="pointer-events-auto absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-2 rounded-md border border-amber-400/30 bg-ink-900/95 px-3 py-1.5 text-xs text-amber-200">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> {error}
        </div>
      )}
    </div>
  )
}
