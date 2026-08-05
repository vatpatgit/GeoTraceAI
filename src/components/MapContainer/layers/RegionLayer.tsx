'use client'

/**
 * RegionLayer — manages GeoJSON region boundaries on a MapLibre map.
 *
 * Responsibilities:
 *   • Load GeoJSON from regionLoader
 *   • Add fill, border, hover, and selected-highlight layers
 *   • Handle click → setSelectedRegion (Zustand)
 *   • Handle hover → border highlight + cursor + name tooltip
 *
 * This component renders no DOM — it manages MapLibre layers imperatively.
 * Mount it inside BaseMap only when the map is loaded:
 *
 *   {mapLoaded && map.current && <RegionLayer map={map.current} mapLib={mapLibRef.current} />}
 *
 * Reusable: swap the GeoJSON source to render any boundary type
 * (countries, states, forests, watersheds).
 */

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { loadRegionGeoJSON } from '@/services/maps/regionLoader'

// ─── Layer IDs (centralized for cleanup + filter updates) ─────────────────────
const LAYER = {
  FILL:            'region-fill',
  BORDER:          'region-border',
  HOVER:           'region-hover',
  SELECTED:        'region-selected',
  SELECTED_BORDER: 'region-selected-border',
} as const

const SOURCE_ID = 'regions'

// ─── Props ────────────────────────────────────────────────────────────────────

interface RegionLayerProps {
  /** The MapLibre Map instance (must be loaded) */
  map: any
  /** The maplibregl module (for Popup constructor) */
  mapLib: any
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function RegionLayer({ map, mapLib }: RegionLayerProps) {
  const { selectedRegion, setSelectedRegion } = useAppStore()
  const hoverPopupRef = useRef<any>(null)

  // ── Add source + layers + event handlers ──────────────────────────────────
  useEffect(() => {
    if (!map || !mapLib) return

    // Hot-reload safety: don't re-add if already present
    if (map.getSource(SOURCE_ID)) return

    // Load GeoJSON from static import
    const geojson = loadRegionGeoJSON()

    map.addSource(SOURCE_ID, {
      type: 'geojson',
      data: geojson,
    })

    // 1. Base fill — very subtle, makes regions clickable
    map.addLayer({
      id: LAYER.FILL,
      type: 'fill',
      source: SOURCE_ID,
      paint: {
        'fill-color': 'rgba(51, 225, 255, 0.04)',
        'fill-opacity': 1,
      },
    })

    // 2. Border lines — subtle region outlines
    map.addLayer({
      id: LAYER.BORDER,
      type: 'line',
      source: SOURCE_ID,
      paint: {
        'line-color': 'rgba(51, 225, 255, 0.25)',
        'line-width': 1.5,
      },
    })

    // 3. Hover highlight fill (filtered to empty initially)
    map.addLayer({
      id: LAYER.HOVER,
      type: 'fill',
      source: SOURCE_ID,
      paint: {
        'fill-color': 'rgba(51, 225, 255, 0.08)',
        'fill-opacity': 1,
      },
      filter: ['==', ['get', 'id'], ''],
    })

    // 4. Selected region fill
    map.addLayer({
      id: LAYER.SELECTED,
      type: 'fill',
      source: SOURCE_ID,
      paint: {
        'fill-color': 'rgba(51, 225, 255, 0.12)',
        'fill-opacity': 1,
      },
      filter: ['==', ['get', 'id'], selectedRegion],
    })

    // 5. Selected region border highlight
    map.addLayer({
      id: LAYER.SELECTED_BORDER,
      type: 'line',
      source: SOURCE_ID,
      paint: {
        'line-color': 'rgba(51, 225, 255, 0.6)',
        'line-width': 2.5,
      },
      filter: ['==', ['get', 'id'], selectedRegion],
    })

    // ── Click handler → setSelectedRegion (same Zustand action as InteractiveMap)
    map.on('click', LAYER.FILL, (e: any) => {
      if (e.features && e.features.length > 0) {
        const regionId = e.features[0].properties?.id
        if (regionId) {
          setSelectedRegion(regionId)
        }
      }
    })

    // ── Hover: highlight border + cursor + tooltip ──────────────────────────
    map.on('mousemove', LAYER.FILL, (e: any) => {
      map.getCanvas().style.cursor = 'pointer'

      if (e.features && e.features.length > 0) {
        const feature = e.features[0]
        const regionId = feature.properties?.id

        // Update hover layer filter
        map.setFilter(LAYER.HOVER, ['==', ['get', 'id'], regionId])

        // Show or update region name tooltip
        const name = feature.properties?.name || ''
        if (!hoverPopupRef.current) {
          hoverPopupRef.current = new mapLib.Popup({
            closeButton: false,
            closeOnClick: false,
            className: 'tt-region-tooltip',
            offset: 16,
          })
        }
        hoverPopupRef.current
          .setLngLat(e.lngLat)
          .setHTML(`<span>${name}</span>`)
          .addTo(map)
      }
    })

    map.on('mouseleave', LAYER.FILL, () => {
      map.getCanvas().style.cursor = ''
      map.setFilter(LAYER.HOVER, ['==', ['get', 'id'], ''])

      if (hoverPopupRef.current) {
        hoverPopupRef.current.remove()
        hoverPopupRef.current = null
      }
    })

    // Cleanup on unmount
    return () => {
      if (hoverPopupRef.current) {
        hoverPopupRef.current.remove()
        hoverPopupRef.current = null
      }
      // Layers and source are cleaned up when map.remove() is called by BaseMap
    }
  }, [map, mapLib]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Update selected highlight when selectedRegion changes ─────────────────
  useEffect(() => {
    if (!map) return

    try {
      const filter = ['==', ['get', 'id'], selectedRegion] as any
      map.setFilter(LAYER.SELECTED, filter)
      map.setFilter(LAYER.SELECTED_BORDER, filter)
    } catch {
      // Layers may not exist yet during initial setup
    }
  }, [selectedRegion, map])

  // This component manages MapLibre layers, not DOM elements
  return null
}
