'use client'

import { weatherFeatureCollection, WEATHER_COLOR } from '@/lib/weather'
import { boxFromCorners } from './drawBox'
import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Globe2 } from 'lucide-react'
import { analysisTileUrl, authHeaders, type FeatureCollectionLite } from '@/lib/api'
import { layerTileUrl } from '@/lib/layers/env'
import { SEVERITY_COLOR } from '@/lib/format'
import { selectActiveAnalysis, useAppStore } from '@/store/useAppStore'
import { useCursorStore } from '@/store/useCursorStore'
import { Button, EmptyBlock } from '@/components/ui/kit'
import { CARTO_DARK_MATTER, ESRI_WORLD_IMAGERY } from '@/services/maps/tileSources'

type CesiumNS = typeof import('cesium')
type Viewer = import('cesium').Viewer

/** Web-Mercator zoom <-> Cesium camera height (assumes ~60 deg vertical FOV and the current viewport height). */
export function zoomToHeight(zoom: number, lat: number, viewportPx: number): number {
  const mpp = (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom
  return (mpp * viewportPx) * 0.866
}
export function heightToZoom(height: number, lat: number, viewportPx: number): number {
  const z = Math.log2((156543.03392 * Math.cos((lat * Math.PI) / 180) * viewportPx * 0.866) / Math.max(height, 1))
  return Math.max(0, Math.min(21, z))
}

function webglSupported(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch { return false }
}

/**
 * CesiumJS 3D globe. Renders the *same* persisted analysis as the 2D map: same polygons (from the shared feature
 * collection), same raster tile endpoints, same layer visibility, same selection and camera requests.
 */
export default function GlobeView({ onSwitch2D }: { onSwitch2D: () => void }) {
  const container = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viewer | null>(null)
  const cesiumRef = useRef<CesiumNS | null>(null)
  const layersRef = useRef<Map<string, import('cesium').ImageryLayer>>(new Map())
  const programmatic = useRef(0)
  const [state, setState] = useState<'loading' | 'ready' | 'unsupported' | 'error'>('loading')
  const [message, setMessage] = useState<string | null>(null)
  const [tileWarning, setTileWarning] = useState<string | null>(null)

  const analysis = useAppStore(selectActiveAnalysis)
  const layerState = useAppStore((s) => s.layerState)
  const catalog = useAppStore((s) => s.layerCatalog)
  const fc = useAppStore((s) => s.featureData.fc)
  const selectedId = useAppStore((s) => s.selectedFeatureId)
  const basemap = useAppStore((s) => s.basemap)
  const flyRequest = useAppStore((s) => s.flyRequest)
  const regions = useAppStore((s) => s.regions)
  const quickCompare = useAppStore((s) => s.quickCompare)
  const quickShow = useAppStore((s) => s.quickShow)
  const weatherAlerts = useAppStore((s) => s.weatherAlerts)
  const selectedWeatherId = useAppStore((s) => s.selectedWeatherId)
  const wxLayer = useAppStore((s) => s.layerState['weather-alerts'])
  const drawMode = useAppStore((s) => s.drawMode)
  const drawnBox = useAppStore((s) => s.drawnBox)

  // ------------------------------------------------------------------------------------------------ init
  useEffect(() => {
    let cancelled = false
    let viewer: Viewer | null = null
    ;(async () => {
      if (!container.current) return
      if (!webglSupported()) { setState('unsupported'); return }
      try {
        ;(window as unknown as { CESIUM_BASE_URL: string }).CESIUM_BASE_URL = '/cesium'
        if (!document.getElementById('cesium-widgets-css')) {
          const link = document.createElement('link')
          link.id = 'cesium-widgets-css'
          link.rel = 'stylesheet'
          link.href = '/cesium/Widgets/widgets.css'
          document.head.appendChild(link)
        }
        const Cesium = await import('cesium')
        if (cancelled || !container.current) return
        cesiumRef.current = Cesium
        Cesium.Ion.defaultAccessToken = '' // never touch Cesium ion: no token is configured or required

        viewer = new Cesium.Viewer(container.current, {
          baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
          navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false, infoBox: false,
          selectionIndicator: false, terrainProvider: new Cesium.EllipsoidTerrainProvider(), requestRenderMode: true,
          maximumRenderTimeChange: Infinity, skyAtmosphere: new Cesium.SkyAtmosphere(),
        })
        viewerRef.current = viewer
        // requestRenderMode only renders on demand, so keep the canvas in step with its container explicitly
        const ro = new ResizeObserver(() => { if (viewer && !viewer.isDestroyed()) { viewer.resize(); viewer.scene.requestRender() } })
        ro.observe(container.current)
        ;(viewer as unknown as { __ro: ResizeObserver }).__ro = ro
        const scene = viewer.scene
        scene.globe.baseColor = Cesium.Color.fromCssColorString('#0b120e')
        scene.globe.showGroundAtmosphere = true
        scene.backgroundColor = Cesium.Color.fromCssColorString('#080D0A')
        scene.globe.depthTestAgainstTerrain = false

        // Bottom: offline Natural Earth II (bundled) so something renders even when every online provider is down.
        try {
          const ne = await Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'))
          viewer.imageryLayers.addImageryProvider(ne)
        } catch { /* optional */ }
        // Basemaps (visibility toggled by state)
        const mk = (id: string, tpl: string[], maximumLevel: number, credit: string) => {
          const p = new Cesium.UrlTemplateImageryProvider({ url: tpl[0], maximumLevel, credit })
          p.errorEvent.addEventListener(() => setTileWarning('Some basemap tiles could not be loaded; showing lower-resolution fallback imagery.'))
          const layer = viewer!.imageryLayers.addImageryProvider(p)
          layersRef.current.set(id, layer)
        }
        mk('basemap-satellite', ESRI_WORLD_IMAGERY.tiles, 19, 'Esri, Maxar, Earthstar Geographics')
        mk('basemap-dark', CARTO_DARK_MATTER.tiles.slice(0, 1).map((t) => t.replace('{z}/{x}/{y}@2x.png', '{z}/{x}/{y}.png')), 20, 'OpenStreetMap contributors, CARTO')

        const st = useAppStore.getState()
        const hpx = container.current.clientHeight || 800
        viewer.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(st.camera.center[0], st.camera.center[1], zoomToHeight(st.camera.zoom, st.camera.center[1], hpx)) })

        // picking
        const handler = new Cesium.ScreenSpaceEventHandler(scene.canvas)
        handler.setInputAction((click: { position: import('cesium').Cartesian2 }) => {
          const picked = scene.pick(click.position)
          const fid = picked?.id?.properties?.fid?.getValue?.() ?? picked?.id?._fid
          useAppStore.getState().selectFeature(fid ?? null)
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
        handler.setInputAction((m: { endPosition: import('cesium').Cartesian2 }) => {
          const ray = viewer!.camera.getPickRay(m.endPosition)
          const p = ray ? scene.globe.pick(ray, scene) : undefined
          if (p) {
            const c = Cesium.Cartographic.fromCartesian(p)
            useCursorStore.getState().set({ lon: Cesium.Math.toDegrees(c.longitude), lat: Cesium.Math.toDegrees(c.latitude) })
          }
        }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)

        viewer.camera.moveEnd.addEventListener(() => {
          const cart = viewer!.camera.positionCartographic
          const lat = Cesium.Math.toDegrees(cart.latitude)
          const zoom = heightToZoom(cart.height, lat, container.current?.clientHeight || 800)
          useCursorStore.getState().set({ zoom, scaleLabel: null })
          if (programmatic.current > 0) { programmatic.current -= 1; return }
          useAppStore.getState().setCamera({ center: [Cesium.Math.toDegrees(cart.longitude), lat], zoom })
        })
        setState('ready')
      } catch (e) {
        if (!cancelled) { setState('error'); setMessage((e as Error).message) }
      }
    })()
    return () => {
      cancelled = true
      // the Map instance is created once and never reassigned, so reading .current here is safe
      // eslint-disable-next-line react-hooks/exhaustive-deps
      layersRef.current.clear()
      ;(viewer as unknown as { __ro?: ResizeObserver } | null)?.__ro?.disconnect()
      if (viewer && !viewer.isDestroyed()) viewer.destroy()
      viewerRef.current = null
    }
  }, [])

  // ------------------------------------------------------------------------------------------------ select an area by dragging a rectangle
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready' || !drawMode) return
    const canvas = viewer.scene.canvas
    const ctl = viewer.scene.screenSpaceCameraController
    const prevInputs = ctl.enableInputs
    ctl.enableInputs = false // dragging must draw, not rotate the globe
    canvas.style.cursor = 'crosshair'
    let start: [number, number] | null = null
    let current: [number, number] | null = null
    const preview = viewer.entities.add({
      rectangle: {
        coordinates: new Cesium.CallbackProperty(() => (start && current ? Cesium.Rectangle.fromDegrees(...boxFromCorners(start, current)) : undefined), false),
        material: Cesium.Color.fromCssColorString('#6EE7A0').withAlpha(0.18), outline: true, outlineColor: Cesium.Color.fromCssColorString('#6EE7A0'), height: 0,
      },
    })
    const pick = (e: PointerEvent): [number, number] | null => {
      const r = canvas.getBoundingClientRect()
      const ray = viewer.camera.getPickRay(new Cesium.Cartesian2(e.clientX - r.left, e.clientY - r.top))
      const p = ray ? viewer.scene.globe.pick(ray, viewer.scene) : undefined
      if (!p) return null
      const c = Cesium.Cartographic.fromCartesian(p)
      return [Cesium.Math.toDegrees(c.longitude), Cesium.Math.toDegrees(c.latitude)]
    }
    const down = (e: PointerEvent) => { const p = pick(e); if (!p) return; start = p; current = p; canvas.setPointerCapture(e.pointerId); viewer.scene.requestRender() }
    const move = (e: PointerEvent) => { if (!start) return; const p = pick(e); if (p) { current = p; viewer.scene.requestRender() } }
    const up = (e: PointerEvent) => {
      if (!start) return
      const end = pick(e) ?? current
      const s0 = start
      start = null; current = null
      canvas.releasePointerCapture(e.pointerId)
      if (end && Math.abs(end[0] - s0[0]) > 1e-5 && Math.abs(end[1] - s0[1]) > 1e-5) {
        const b = boxFromCorners(s0, end)
        useAppStore.getState().setDrawnBox([+b[0].toFixed(5), +b[1].toFixed(5), +b[2].toFixed(5), +b[3].toFixed(5)])
        useAppStore.getState().setDrawMode(false)
      }
      viewer.scene.requestRender()
    }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerup', up)
    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerup', up)
      canvas.style.cursor = ''
      if (!viewer.isDestroyed()) { ctl.enableInputs = prevInputs; viewer.entities.remove(preview); viewer.scene.requestRender() }
    }
  }, [drawMode, state])

  // the selected rectangle stays visible until it is cleared
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready' || !drawnBox) return
    const e = viewer.entities.add({
      rectangle: { coordinates: Cesium.Rectangle.fromDegrees(...drawnBox), material: Cesium.Color.fromCssColorString('#6EE7A0').withAlpha(0.15), outline: true, outlineColor: Cesium.Color.fromCssColorString('#6EE7A0'), height: 0 },
    })
    viewer.scene.requestRender()
    return () => { if (!viewer.isDestroyed()) { viewer.entities.remove(e); viewer.scene.requestRender() } }
  }, [drawnBox, state])

  // ------------------------------------------------------------------------------------------------ provider weather alerts
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready') return
    let cancelled = false
    let ds: import('cesium').GeoJsonDataSource | null = null
    const fc = weatherFeatureCollection(weatherAlerts, selectedWeatherId)
    if (!(wxLayer?.visible ?? true) || fc.features.length === 0) return
    ;(async () => {
      const loaded = await Cesium.GeoJsonDataSource.load(fc as unknown as object, { clampToGround: true })
      if (cancelled || viewer.isDestroyed()) return
      ds = loaded
      const alpha = Math.max(0.05, Math.min(1, (wxLayer?.opacity ?? 0.45) * 0.7))
      for (const e of ds.entities.values) {
        const sev = (e.properties?.severity?.getValue?.() ?? 'unknown') as keyof typeof WEATHER_COLOR
        const sel = e.properties?.selected?.getValue?.() === 1
        const color = Cesium.Color.fromCssColorString(WEATHER_COLOR[sev] ?? WEATHER_COLOR.unknown)
        if (e.polygon) {
          e.polygon.material = new Cesium.ColorMaterialProperty(color.withAlpha(alpha))
          e.polygon.outline = new Cesium.ConstantProperty(true)
          e.polygon.outlineColor = new Cesium.ConstantProperty(color)
          e.polygon.outlineWidth = new Cesium.ConstantProperty(sel ? 4 : 2)
        }
        if (e.billboard) e.billboard = undefined
        if (!e.polygon && e.position) e.point = new Cesium.PointGraphics({ pixelSize: sel ? 16 : 11, color, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 })
      }
      viewer.dataSources.add(ds)
      viewer.scene.requestRender()
    })()
    return () => { cancelled = true; if (ds && !viewer.isDestroyed()) { viewer.dataSources.remove(ds, true); viewer.scene.requestRender() } }
  }, [weatherAlerts, selectedWeatherId, wxLayer, state])

  // ------------------------------------------------------------------------------------------------ on-demand Sentinel-2 images
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready') return
    const reg = layersRef.current
    if (!quickCompare) {
      for (const id of ['quick-before', 'quick-after']) { const old = reg.get(id); if (old) { viewer.imageryLayers.remove(old, true); reg.delete(id) } }
      viewer.scene.requestRender()
      return
    }
    let cancelled = false
    ;(async () => {
      for (const [id, scene] of [['quick-before', quickCompare.before], ['quick-after', quickCompare.after]] as const) {
        const old = reg.get(id)
        if (old && (old as unknown as { __url?: string }).__url === scene.url) continue
        if (old) { viewer.imageryLayers.remove(old, true); reg.delete(id) }
        const provider = await Cesium.SingleTileImageryProvider.fromUrl(scene.url, { rectangle: Cesium.Rectangle.fromDegrees(...quickCompare.bbox) })
        if (cancelled) return
        const layer = viewer.imageryLayers.addImageryProvider(provider)
        ;(layer as unknown as { __url?: string }).__url = scene.url
        reg.set(id, layer)
      }
      for (const [id, key] of [['quick-before', 'before'], ['quick-after', 'after']] as const) { const l = reg.get(id); if (l) l.show = quickShow === key }
      viewer.scene.requestRender()
    })()
    return () => { cancelled = true }
  }, [quickCompare, quickShow, state])

  // ------------------------------------------------------------------------------------------------ layers
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready') return
    const reg = layersRef.current
    const setBasemaps = () => {
      const sat = reg.get('basemap-satellite'); const dark = reg.get('basemap-dark')
      if (sat) sat.show = basemap === 'satellite'
      if (dark) dark.show = basemap === 'dark'
    }
    setBasemaps()

    const want = new Map<string, { url: string; alpha: number; visible: boolean; rect?: import('cesium').Rectangle; maxLevel: number; auth?: boolean }>()
    if (analysis && analysis.status === 'completed') {
      const rect = analysis.bounds ? Cesium.Rectangle.fromDegrees(...analysis.bounds) : undefined
      const add = (id: string, layer: 'before' | 'after' | 'score' | 'delta_ndvi', stateId: string) => {
        const st = layerState[stateId]
        if (st?.visible) want.set(id, { url: analysisTileUrl(analysis.id, layer), alpha: st.opacity, visible: true, rect, maxLevel: 21 })
      }
      add(`an-before-${analysis.id}`, 'before', 'imagery-before')
      add(`an-after-${analysis.id}`, 'after', 'imagery-after')
      add(`an-score-${analysis.id}`, 'score', 'change-score')
      if (analysis.processing?.grid?.roles?.includes('nir')) add(`an-dndvi-${analysis.id}`, 'delta_ndvi', 'delta-ndvi')
    }
    for (const l of catalog) {
      if (l.group === 'change') continue
      const st = layerState[l.id]; const url = layerTileUrl(l, analysis, 'cesium')
      if (st?.visible && url) want.set(`env-${l.id}`, { url, alpha: st.opacity, visible: true, maxLevel: l.max_zoom ?? 9, auth: l.render_type === 'analysis_raster', rect: l.render_type === 'analysis_raster' && analysis?.bounds ? Cesium.Rectangle.fromDegrees(...analysis.bounds) : undefined })
    }
    // remove stale
    for (const [id, layer] of Array.from(reg.entries())) {
      if (id.startsWith('basemap') || id.startsWith('quick-')) continue
      if (!want.has(id)) { viewer.imageryLayers.remove(layer, true); reg.delete(id) }
    }
    // add / update
    for (const [id, w] of want) {
      const existing = reg.get(id)
      if (existing) { existing.alpha = w.alpha; continue }
      const resource = new Cesium.Resource({ url: w.url, headers: id.startsWith('env-') && !w.auth ? {} : authHeaders() })
      const provider = new Cesium.UrlTemplateImageryProvider({ url: resource, maximumLevel: w.maxLevel, rectangle: w.rect, tilingScheme: new Cesium.WebMercatorTilingScheme() })
      provider.errorEvent.addEventListener(() => setTileWarning(`Layer tiles failed to load (${id.replace(/^(an|env)-/, '')}).`))
      const layer = viewer.imageryLayers.addImageryProvider(provider)
      layer.alpha = w.alpha
      reg.set(id, layer)
    }
    viewer.scene.requestRender()
  }, [analysis, layerState, catalog, basemap, state])

  // ------------------------------------------------------------------------------------------------ polygons
  const dsRef = useRef<import('cesium').CustomDataSource | null>(null)
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready') return
    if (!dsRef.current) {
      dsRef.current = new Cesium.CustomDataSource('changes')
      void viewer.dataSources.add(dsRef.current)
    }
    const ds = dsRef.current
    ds.entities.removeAll()
    const showChange = layerState['change-polygons']?.visible !== false
    const showAoi = layerState['aoi']?.visible !== false
    if (showChange) addFeatures(Cesium, ds, fc, selectedId)
    if (showAoi && analysis?.bounds) {
      const [w, s, e, n] = analysis.bounds
      ds.entities.add({ id: 'aoi-outline', polyline: { positions: Cesium.Cartesian3.fromDegreesArray([w, s, e, s, e, n, w, n, w, s]), width: 1.6, clampToGround: true, material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.fromCssColorString('#6EE7A0'), dashLength: 14 }) } })
    }
    if (showAoi) {
      for (const r of regions) {
        const g = r.geometry as { type: string; coordinates: number[][][] } | null
        if (g?.type === 'Polygon') ds.entities.add({ id: `region-${r.id}`, polyline: { positions: Cesium.Cartesian3.fromDegreesArray(g.coordinates[0].flat()), width: 1.2, clampToGround: true, material: Cesium.Color.fromCssColorString('#818CF8').withAlpha(0.8) } })
      }
    }
    viewer.scene.requestRender()
  }, [fc, selectedId, layerState, analysis, regions, state])

  // ------------------------------------------------------------------------------------------------ camera requests
  const lastFly = useRef(0)
  useEffect(() => {
    const viewer = viewerRef.current
    const Cesium = cesiumRef.current
    if (!viewer || !Cesium || state !== 'ready' || !flyRequest || flyRequest.id === lastFly.current) return
    lastFly.current = flyRequest.id
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    programmatic.current += 1
    if (flyRequest.bbox) {
      const [w, s, e, n] = flyRequest.bbox
      const padX = Math.max((e - w) * 0.35, 0.002); const padY = Math.max((n - s) * 0.35, 0.002)
      viewer.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(w - padX, s - padY, e + padX, n + padY), duration: reduce ? 0 : 1.6 })
    } else if (flyRequest.center) {
      const hpx = container.current?.clientHeight || 800
      viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(flyRequest.center[0], flyRequest.center[1], zoomToHeight(flyRequest.zoom ?? 14, flyRequest.center[1], hpx)), duration: reduce ? 0 : 1.6 })
    }
  }, [flyRequest, state])

  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" role="application" aria-label="3D globe" />
      {state === 'loading' && <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500">Starting 3D globe...</div>}
      {state === 'unsupported' && (
        <div className="absolute inset-0 flex items-center justify-center bg-ink-950">
          <EmptyBlock icon={<Globe2 className="h-7 w-7" />} title="3D globe needs WebGL" hint="This browser or device does not expose WebGL. The 2D map shows the same analysis." action={<Button tone="accent" onClick={onSwitch2D}>Open 2D map</Button>} />
        </div>
      )}
      {state === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center bg-ink-950">
          <EmptyBlock icon={<AlertTriangle className="h-7 w-7 text-amber-400" />} title="The 3D globe could not start" hint={message ?? undefined} action={<Button tone="accent" onClick={onSwitch2D}>Open 2D map</Button>} />
        </div>
      )}
      {tileWarning && state === 'ready' && (
        <div role="status" className="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-2 rounded-md border border-amber-400/30 bg-ink-900/95 px-3 py-1.5 text-xs text-amber-200">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> {tileWarning}
          <button className="ml-1 text-amber-300/70 hover:text-amber-100" onClick={() => setTileWarning(null)} aria-label="Dismiss">&times;</button>
        </div>
      )}
      <div className="pointer-events-none absolute bottom-1.5 right-2 z-10 text-2xs text-slate-600">Imagery: Esri / Natural Earth II &middot; CesiumJS</div>
    </div>
  )
}

function addFeatures(Cesium: CesiumNS, ds: import('cesium').CustomDataSource, fc: FeatureCollectionLite | null, selectedId: string | null) {
  if (!fc) return
  for (const f of fc.features) {
    const sel = f.id === selectedId || f.properties.id === selectedId
    const color = Cesium.Color.fromCssColorString(SEVERITY_COLOR[f.properties.severity])
    const g = f.geometry as { type: string; coordinates: number[][][] | number[][][][] }
    const polys: number[][][][] = g.type === 'Polygon' ? [g.coordinates as number[][][]] : (g.coordinates as number[][][][])
    polys.forEach((rings, k) => {
      const outer = rings[0].flat()
      const holes = rings.slice(1).map((r) => new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(r.flat())))
      const id = `${f.id}:${k}`
      const entity = ds.entities.add({
        id,
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(outer), holes),
          material: color.withAlpha(f.properties.review_status === 'rejected' ? 0.1 : sel ? 0.55 : 0.32),
          classificationType: Cesium.ClassificationType.BOTH,
        },
        polyline: { positions: Cesium.Cartesian3.fromDegreesArray(outer), width: sel ? 4 : 2, clampToGround: true, material: sel ? Cesium.Color.WHITE : color },
        properties: { fid: f.id },
      })
      ;(entity as unknown as { _fid: string })._fid = f.id
    })
  }
}
