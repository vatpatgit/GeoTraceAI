'use client'

import { useEffect, useRef } from 'react'
import type { Map as MlMap } from 'maplibre-gl'
import { assetTileUrl, type BBox } from '@/lib/api'
import { loadMapLibrary } from '@/services/maps/mapProvider'
import { transformRequest } from '@/components/map/maplibreLayers'
import { baseStyle } from '@/components/map/basemaps'

/** Small non-store-bound map previewing one validated raster (its tiles come from the access-controlled API). */
export default function AssetMap({ assetId, bounds, label }: { assetId: string | null; bounds: BBox | null; label: string }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)

  useEffect(() => {
    if (!el.current) return
    let cancelled = false
    ;(async () => {
      const lib = await loadMapLibrary()
      if (cancelled || !el.current) return
      const map = new lib.Map({ container: el.current, style: baseStyle('dark'), center: [0, 20], zoom: 1, attributionControl: false, transformRequest, interactive: true }) as MlMap
      mapRef.current = map
      map.addControl(new lib.NavigationControl({ showCompass: false }), 'top-right')
    })()
    return () => { cancelled = true; mapRef.current?.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => {
      if (map.getLayer('asset')) map.removeLayer('asset')
      if (map.getSource('asset')) map.removeSource('asset')
      if (map.getLayer('asset-outline')) map.removeLayer('asset-outline')
      if (map.getSource('asset-outline')) map.removeSource('asset-outline')
      if (!assetId || !bounds) return
      map.addSource('asset', { type: 'raster', tiles: [assetTileUrl(assetId)], tileSize: 256, maxzoom: 22 })
      map.addLayer({ id: 'asset', type: 'raster', source: 'asset', paint: { 'raster-fade-duration': 0 } })
      const [w, s, e, n] = bounds
      map.addSource('asset-outline', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } } })
      map.addLayer({ id: 'asset-outline', type: 'line', source: 'asset-outline', paint: { 'line-color': '#2DD4BF', 'line-width': 1.5, 'line-dasharray': [3, 2] } })
      map.fitBounds([[w, s], [e, n]], { padding: 24, duration: 0, maxZoom: 18 })
    }
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
  }, [assetId, bounds])

  return (
    <div className="relative h-52 overflow-hidden rounded-md border border-white/10 bg-black/40">
      <div ref={el} className="h-full w-full" role="img" aria-label={`${label} imagery preview map`} />
      <span className="pointer-events-none absolute left-2 top-2 rounded bg-ink-900/85 px-1.5 py-0.5 font-mono text-2xs uppercase tracking-wider text-slate-300">{label}</span>
      {!assetId && <div className="absolute inset-0 flex items-center justify-center text-2xs text-slate-600">No imagery yet</div>}
    </div>
  )
}
