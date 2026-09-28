'use client'

/**
 * SentinelImageryLayer — backend-driven Sentinel-2 imagery for the active region/date.
 *
 * Fetches PNG imagery from POST /api/v1/sentinel/imagery and renders it as a MapLibre
 * georeferenced image layer above the ESRI fallback base tiles.
 */

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { bboxToImageCoordinates, fetchSentinelImagery } from '@/lib/sentinelApi'
import type { Region } from '@/types'

export type SentinelImageryStatus =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'loaded'; date: string }
  | { state: 'error'; message: string }

const ESRI_LAYER_IDS = ['satellite-base-layer', 'satellite-layer']
const SOURCE_ID = 'sentinel-imagery'
const LAYER_ID = 'sentinel-imagery-layer'
const REGION_FILL_LAYER = 'region-fill'

interface SentinelImageryLayerProps {
  map: any
  regions: Region[]
  onStatusChange?: (status: SentinelImageryStatus) => void
}

function setEsriBaseVisibility(map: any, visible: boolean) {
  for (const id of ESRI_LAYER_IDS) {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
    }
  }
}

function removeSentinelImagery(map: any) {
  if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID)
  if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID)
}

function placeSentinelLayer(map: any, opacity: number) {
  if (map.getLayer(LAYER_ID)) {
    map.setPaintProperty(LAYER_ID, 'raster-opacity', opacity)
    return
  }

  const layerDef = {
    id: LAYER_ID,
    type: 'raster',
    source: SOURCE_ID,
    paint: { 'raster-opacity': opacity },
  }

  if (map.getLayer(REGION_FILL_LAYER)) {
    map.addLayer(layerDef, REGION_FILL_LAYER)
    return
  }

  map.addLayer(layerDef)

  const moveBelowRegions = () => {
    if (map.getLayer(REGION_FILL_LAYER) && map.getLayer(LAYER_ID)) {
      map.moveLayer(LAYER_ID, REGION_FILL_LAYER)
      map.off('styledata', moveBelowRegions)
    }
  }
  map.on('styledata', moveBelowRegions)
}

export default function SentinelImageryLayer({ map, regions, onStatusChange }: SentinelImageryLayerProps) {
  const { selectedRegion, selectedDate, authStatus, layerVisibility } = useAppStore()
  const blobUrlRef = useRef<string | null>(null)
  const requestIdRef = useRef(0)

  const satelliteVisible = layerVisibility.satellite?.visible ?? true
  const satelliteOpacity = layerVisibility.satellite?.opacity ?? 1

  useEffect(() => {
    if (!map) return

    const revokeBlobUrl = () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }

    const resetToFallback = (status: SentinelImageryStatus) => {
      revokeBlobUrl()
      removeSentinelImagery(map)
      setEsriBaseVisibility(map, true)
      onStatusChange?.(status)
    }

    if (!satelliteVisible || authStatus !== 'authenticated' || !selectedRegion) {
      resetToFallback({ state: 'idle' })
      return
    }

    const region = regions.find((item) => item.id === selectedRegion)
    if (!region) {
      resetToFallback({ state: 'idle' })
      return
    }

    const requestId = ++requestIdRef.current
    let cancelled = false

    onStatusChange?.({ state: 'loading' })

    fetchSentinelImagery(selectedRegion, selectedDate, { width: 1024, height: 1024 })
      .then((blob) => {
        if (cancelled || requestId !== requestIdRef.current) return

        revokeBlobUrl()
        const url = URL.createObjectURL(blob)
        blobUrlRef.current = url

        const coordinates = bboxToImageCoordinates(region.bbox)
        const existingSource = map.getSource(SOURCE_ID)

        if (existingSource) {
          existingSource.updateImage({ url, coordinates })
        } else {
          map.addSource(SOURCE_ID, { type: 'image', url, coordinates })
          placeSentinelLayer(map, satelliteOpacity)
        }

        map.setLayoutProperty(LAYER_ID, 'visibility', 'visible')
        map.setPaintProperty(LAYER_ID, 'raster-opacity', satelliteOpacity)
        setEsriBaseVisibility(map, false)
        onStatusChange?.({ state: 'loaded', date: selectedDate })
      })
      .catch((error: Error) => {
        if (cancelled || requestId !== requestIdRef.current) return
        resetToFallback({ state: 'error', message: 'Sentinel-2 unavailable' })
      })

    return () => {
      cancelled = true
    }
  }, [
    map,
    regions,
    selectedRegion,
    selectedDate,
    authStatus,
    satelliteVisible,
    satelliteOpacity,
    onStatusChange,
  ])

  useEffect(() => {
    if (!map || !map.getLayer(LAYER_ID)) return

    const visibility = satelliteVisible ? 'visible' : 'none'
    map.setLayoutProperty(LAYER_ID, 'visibility', visibility)
    map.setPaintProperty(LAYER_ID, 'raster-opacity', satelliteOpacity)

    if (!satelliteVisible) {
      setEsriBaseVisibility(map, true)
    } else if (blobUrlRef.current) {
      setEsriBaseVisibility(map, false)
    }
  }, [map, satelliteVisible, satelliteOpacity])

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [])

  return null
}
