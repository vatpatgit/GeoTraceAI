'use client'

/**
 * ChangeDetectionLayer — manages change detection overlays on the MapLibre map.
 *
 * Fetches detected change polygons via fetchChanges(regionId, selectedDate)
 * and renders high-visibility semi-transparent fills and glowing stroke boundaries.
 *
 * Fully reactive to store layer visibility, date, and selected region.
 */

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { fetchChanges } from '@/lib/mockApi'
import type { ChangeFeatureCollection } from '@/types'

const SOURCE_ID = 'terratrack-change-detection'
const FILL_LAYER_ID = 'change-detection-fill'
const LINE_LAYER_ID = 'change-detection-line'

interface ChangeDetectionLayerProps {
  map: any
  mapLib: any
}

export default function ChangeDetectionLayer({ map, mapLib }: ChangeDetectionLayerProps) {
  const { selectedRegion, selectedDate, layerVisibility } = useAppStore()
  const changeLayerState = layerVisibility['change-detection']
  const visible = changeLayerState?.visible ?? true
  const opacity = changeLayerState?.opacity ?? 0.85
  const popupRef = useRef<any>(null)

  useEffect(() => {
    if (!map || !mapLib) return

    let cancelled = false

    const removeLayers = () => {
      if (popupRef.current) {
        popupRef.current.remove()
        popupRef.current = null
      }
      if (map.getLayer(LINE_LAYER_ID)) map.removeLayer(LINE_LAYER_ID)
      if (map.getLayer(FILL_LAYER_ID)) map.removeLayer(FILL_LAYER_ID)
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID)
    }

    if (!visible || !selectedRegion) {
      removeLayers()
      return
    }

    fetchChanges(selectedRegion, selectedDate)
      .then((data: ChangeFeatureCollection | null) => {
        if (cancelled || !data || !data.features || data.features.length === 0) {
          removeLayers()
          return
        }

        const existingSource = map.getSource(SOURCE_ID)
        if (existingSource) {
          existingSource.setData(data)
        } else {
          map.addSource(SOURCE_ID, {
            type: 'geojson',
            data,
          })

          // Semi-transparent alert fill
          map.addLayer({
            id: FILL_LAYER_ID,
            type: 'fill',
            source: SOURCE_ID,
            paint: {
              'fill-color': [
                'match',
                ['get', 'change_type'],
                'deforestation', '#EF4444',
                'wildfire', '#F97316',
                'water_loss', '#06B6D4',
                'urban_expansion', '#A855F7',
                '#F59E0B',
              ],
              'fill-opacity': opacity * 0.45,
            },
          })

          // Glowing border outline
          map.addLayer({
            id: LINE_LAYER_ID,
            type: 'line',
            source: SOURCE_ID,
            paint: {
              'line-color': [
                'match',
                ['get', 'change_type'],
                'deforestation', '#EF4444',
                'wildfire', '#F97316',
                'water_loss', '#06B6D4',
                'urban_expansion', '#A855F7',
                '#F59E0B',
              ],
              'line-width': 2,
              'line-opacity': opacity,
            },
          })

          // Hover interaction for change features
          map.on('mouseenter', FILL_LAYER_ID, (e: any) => {
            map.getCanvas().style.cursor = 'pointer'
            if (!e.features || !e.features[0]) return

            const props = e.features[0].properties || {}
            const type = (props.change_type || 'Environmental Change').replace(/_/g, ' ')
            const conf = props.confidence ? Math.round(Number(props.confidence) * 100) : 85

            if (!popupRef.current) {
              popupRef.current = new mapLib.Popup({
                closeButton: false,
                closeOnClick: false,
                className: 'terratrack-change-popup',
                offset: 12,
              })
            }

            popupRef.current
              .setLngLat(e.lngLat)
              .setHTML(
                `<div style="background:#0D1321;border:1px solid rgba(239,68,68,0.4);border-radius:6px;padding:8px 12px;color:#fff;font-family:sans-serif;font-size:11px;box-shadow:0 4px 12px rgba(0,0,0,0.5);">` +
                  `<div style="font-weight:700;color:#F87171;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px;">⚠️ ${type}</div>` +
                  `<div style="color:#94A3B8;">Confidence: <span style="color:#33E1FF;font-weight:600;">${conf}%</span></div>` +
                  `<div style="color:#64748B;font-size:10px;margin-top:2px;">TerraTrack Change Detection</div>` +
                `</div>`
              )
              .addTo(map)
          })

          map.on('mouseleave', FILL_LAYER_ID, () => {
            map.getCanvas().style.cursor = ''
            if (popupRef.current) {
              popupRef.current.remove()
              popupRef.current = null
            }
          })
        }

        if (map.getLayer(FILL_LAYER_ID)) {
          map.setLayoutProperty(FILL_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
          map.setPaintProperty(FILL_LAYER_ID, 'fill-opacity', opacity * 0.45)
        }
        if (map.getLayer(LINE_LAYER_ID)) {
          map.setLayoutProperty(LINE_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
          map.setPaintProperty(LINE_LAYER_ID, 'line-opacity', opacity)
        }
      })
      .catch(() => {
        removeLayers()
      })

    return () => {
      cancelled = true
    }
  }, [map, mapLib, selectedRegion, selectedDate, visible, opacity])

  // React to visibility / opacity updates without refetching
  useEffect(() => {
    if (!map) return
    if (map.getLayer(FILL_LAYER_ID)) {
      map.setLayoutProperty(FILL_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
      map.setPaintProperty(FILL_LAYER_ID, 'fill-opacity', opacity * 0.45)
    }
    if (map.getLayer(LINE_LAYER_ID)) {
      map.setLayoutProperty(LINE_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
      map.setPaintProperty(LINE_LAYER_ID, 'line-opacity', opacity)
    }
  }, [map, visible, opacity])

  return null
}
