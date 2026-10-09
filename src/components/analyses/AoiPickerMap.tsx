'use client'

import { useEffect, useRef } from 'react'
import type { Map as MlMap } from 'maplibre-gl'
import { loadMapLibrary } from '@/services/maps/mapProvider'
import { baseStyle } from '@/components/map/basemaps'
import type { Position } from '@/lib/api'

/** Approximate geodesic circle (for display only; the server builds the authoritative AOI polygon). */
export function circleCoords(center: Position, radiusM: number, n = 64): number[][] {
  const [lon, lat] = center
  const dLat = radiusM / 111_320
  const dLon = radiusM / (111_320 * Math.max(Math.cos((lat * Math.PI) / 180), 0.01))
  const ring: number[][] = []
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)])
  }
  return ring
}

export default function AoiPickerMap({ center, radiusM, onPick, scenes }: { center: Position | null; radiusM: number; onPick: (p: Position) => void; scenes?: unknown[] }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const pickRef = useRef(onPick)
  pickRef.current = onPick

  useEffect(() => {
    if (!el.current) return
    let cancelled = false
    ;(async () => {
      const lib = await loadMapLibrary()
      if (cancelled || !el.current) return
      const map = new lib.Map({ container: el.current, style: baseStyle('satellite'), center: center ?? [10, 20], zoom: center ? 9 : 1.5, attributionControl: { compact: true } }) as MlMap
      mapRef.current = map
      map.addControl(new lib.NavigationControl({ showCompass: false }), 'top-right')
      map.getCanvas().style.cursor = 'crosshair'
      map.on('click', (e) => pickRef.current([Number(e.lngLat.lng.toFixed(5)), Number(e.lngLat.lat.toFixed(5))]))
      const ro = new ResizeObserver(() => map.resize())
      ro.observe(el.current)
      map.on('remove', () => ro.disconnect())
    })()
    return () => { cancelled = true; mapRef.current?.remove(); mapRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => {
      const data = { type: 'FeatureCollection' as const, features: center ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [circleCoords(center, radiusM)] } }] : [] }
      const src = map.getSource('aoi') as import('maplibre-gl').GeoJSONSource | undefined
      if (src) src.setData(data)
      else {
        map.addSource('aoi', { type: 'geojson', data })
        map.addLayer({ id: 'aoi-fill', type: 'fill', source: 'aoi', paint: { 'fill-color': '#6EE7A0', 'fill-opacity': 0.15 } })
        map.addLayer({ id: 'aoi-line', type: 'line', source: 'aoi', paint: { 'line-color': '#6EE7A0', 'line-width': 2 } })
      }
    }
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [center, radiusM])

  useEffect(() => {
    const map = mapRef.current
    if (map && center) map.easeTo({ center, zoom: Math.max(map.getZoom(), 9), duration: 600 })
  }, [center])

  return <div ref={el} className="h-64 w-full overflow-hidden rounded-md border border-[color:var(--line-strong)]" role="application" aria-label="Click the map to set the area centre" />
}
