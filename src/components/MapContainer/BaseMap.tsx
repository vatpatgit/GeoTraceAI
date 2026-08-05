'use client'

import { useRef, useEffect, useState, useCallback } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { REGION_CENTERS, getRecentAlerts, MAP_REGIONS } from '@/lib/mockData'
import type { MapRegion } from '@/lib/mockData'
import { loadMapLibrary } from '@/services/maps/mapProvider'
import { createSatelliteStyle } from '@/services/maps/mapStyle'
import RegionLayer from './layers/RegionLayer'
import AlertMarkerLayer from './layers/AlertMarkerLayer'

// ─── BaseMap Component ────────────────────────────────────────────────────────
export default function BaseMap() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<any>(null)
  const mapLibRef = useRef<any>(null)         // holds the dynamically-imported GL library
  const [mapLoaded, setMapLoaded] = useState(false)
  const [mapError, setMapError] = useState(false)
  const [mapInitializing, setMapInitializing] = useState(true)
  const { mapView, updateMapCenter, updateZoom, selectedRegion } = useAppStore()

  // Initialize map — dynamic import avoids SSR issues entirely
  useEffect(() => {
    if (!mapContainer.current || map.current) return

    let cancelled = false

    async function initMap() {
      try {
        const maplibregl = await loadMapLibrary()
        if (cancelled || !mapContainer.current) return

        mapLibRef.current = maplibregl

        const mapInstance = new maplibregl.Map({
          container: mapContainer.current,
          style: createSatelliteStyle(),
          center: mapView.center,
          zoom: mapView.zoom,
          pitch: 0,
          bearing: 0,
          attributionControl: true,
        })

        map.current = mapInstance

        mapInstance.on('load', () => {
          if (!cancelled) {
            setMapLoaded(true)
            setMapInitializing(false)
          }
        })

        mapInstance.on('error', () => {
          if (!cancelled) {
            setMapError(true)
            setMapInitializing(false)
          }
        })

        mapInstance.on('moveend', () => {
          if (!map.current) return
          const center = map.current.getCenter()
          const zoom = map.current.getZoom()
          updateMapCenter([center.lng, center.lat])
          updateZoom(zoom)
        })

        mapInstance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
      } catch {
        if (!cancelled) {
          setMapError(true)
          setMapInitializing(false)
        }
      }
    }

    initMap()

    // Cleanup: remove map instance and markers on unmount / hot-reload
    return () => {
      cancelled = true
      if (map.current) {
        map.current.remove()
        map.current = null
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Fly to region when selected region changes
  useEffect(() => {
    const rc = REGION_CENTERS[selectedRegion]
    if (!rc) return

    if (map.current && mapLoaded) {
      map.current.flyTo({
        center: rc.center,
        zoom: rc.zoom,
        duration: 2000,
        essential: true,
      })
    }
  }, [selectedRegion, mapLoaded])

  // Alert markers are now managed by AlertMarkerLayer

  // Fallback: enhanced interactive mock map
  if (mapError) {
    return <InteractiveMap />
  }

  return (
    <div className="relative w-full h-full" style={{ minHeight: '400px' }}>
      {/* Loading skeleton — themed spinner while map downloads tiles */}
      {mapInitializing && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0A0F1C]">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 border-2 border-[#33E1FF]/30 border-t-[#33E1FF] rounded-full animate-spin" />
            <span className="text-sm text-slate-400 tracking-wide">Loading satellite imagery…</span>
          </div>
        </div>
      )}
      <div ref={mapContainer} className="w-full h-full" style={{ minHeight: '400px' }} />
      {/* Region boundaries — delegated to RegionLayer */}
      {mapLoaded && map.current && mapLibRef.current && (
        <>
          <RegionLayer map={map.current} mapLib={mapLibRef.current} />
          <AlertMarkerLayer map={map.current} mapLib={mapLibRef.current} />
        </>
      )}
    </div>
  )
}

// ─── Interactive Mock Map with Clickable Regions ──────────────────────────────

function InteractiveMap() {
  const { selectedRegion, setSelectedRegion } = useAppStore()
  const rc = REGION_CENTERS[selectedRegion]

  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  // Convert polygon points to SVG points string
  const toSvgPoints = useCallback((polygon: [number, number][]) => {
    return polygon.map(([x, y]) => `${x},${y}`).join(' ')
  }, [])

  // Handle region click
  const handleRegionClick = useCallback((regionId: string) => {
    setSelectedRegion(regionId)
  }, [setSelectedRegion])

  // Handle mouse move for tooltip
  const handleRegionHover = useCallback((e: React.MouseEvent, region: MapRegion | null) => {
    if (region) {
      setHoveredRegion(region.id)
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        setTooltipPos({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
        })
      }
    } else {
      setHoveredRegion(null)
    }
  }, [])

  // Get all alerts for all regions for alert markers
  const allAlerts = MAP_REGIONS.map((region) => ({
    region,
    alerts: getRecentAlerts(region.id),
  }))

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden select-none"
      style={{ minHeight: '400px' }}
    >
      {/* Animated satellite-style background */}
      <div className="absolute inset-0 mock-map-bg" />

      {/* Grid overlay */}
      <div className="absolute inset-0 mock-map-grid opacity-20" />

      {/* Scan line animation */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="mock-scanline" />
      </div>

      {/* ── SVG Interactive Region Layer ─────────────────────────────── */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ zIndex: 10 }}
      >
        <defs>
          {/* Glow filters per region */}
          {MAP_REGIONS.map((region) => (
            <filter key={`filter-${region.id}`} id={`glow-${region.id}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="1" result="blur" />
              <feFlood floodColor={region.color} floodOpacity="0.6" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}
        </defs>

        {MAP_REGIONS.map((region) => {
          const isSelected = selectedRegion === region.id
          const isHovered = hoveredRegion === region.id

          return (
            <polygon
              key={region.id}
              points={toSvgPoints(region.polygon)}
              className={`region-polygon ${isSelected ? 'selected' : ''}`}
              style={{
                fill: isSelected
                  ? `${region.color}20`
                  : isHovered
                  ? `${region.color}12`
                  : undefined,
                stroke: isSelected
                  ? region.color
                  : isHovered
                  ? `${region.color}99`
                  : undefined,
                ['--region-glow' as any]: `${region.color}80`,
                filter: isSelected ? `url(#glow-${region.id})` : undefined,
              }}
              onClick={() => handleRegionClick(region.id)}
              onMouseMove={(e) => handleRegionHover(e, region)}
              onMouseLeave={() => handleRegionHover(null as any, null)}
              id={`map-region-${region.id}`}
            />
          )
        })}
      </svg>

      {/* ── Change Detection Zone Overlays ───────────────────────────── */}
      {MAP_REGIONS.map((region) =>
        region.changeZones.map((zone, i) => {
          const isActive = selectedRegion === region.id
          return (
            <div
              key={`zone-${region.id}-${i}`}
              className="change-zone-overlay"
              style={{
                left: `${zone[0]}%`,
                top: `${zone[1]}%`,
                width: `${zone[2]}%`,
                height: `${zone[3]}%`,
                background: isActive
                  ? `${region.color}18`
                  : 'rgba(239, 68, 68, 0.08)',
                border: `1px solid ${isActive ? `${region.color}40` : 'rgba(239, 68, 68, 0.15)'}`,
                animationDelay: `${i * 1.2}s`,
                zIndex: 8,
              }}
            />
          )
        })
      )}

      {/* ── Alert Markers (pulsing dots) ─────────────────────────────── */}
      {allAlerts.map(({ region, alerts }) =>
        alerts.map((alert, i) => {
          const pos = region.alertPositions[i]
          if (!pos) return null

          const color =
            alert.severity === 'critical'
              ? '#EF4444'
              : alert.severity === 'warning'
              ? '#F59E0B'
              : '#3B82F6'

          return (
            <div key={alert.id} className="group" style={{ position: 'absolute', left: `${pos[0]}%`, top: `${pos[1]}%`, zIndex: 15 }}>
              {/* Pulse ring */}
              <div
                className="map-alert-ring animate-ping"
                style={{
                  background: `${color}30`,
                  animationDuration: `${2 + i * 0.5}s`,
                }}
              />
              {/* Dot */}
              <div
                className="map-alert-dot"
                style={{
                  background: color,
                  boxShadow: `0 0 10px ${color}80`,
                }}
              />
              {/* Hover tooltip */}
              <div className="absolute left-5 top-0 hidden group-hover:block z-30 min-w-[200px]">
                <div className="glass-card rounded-lg p-3 text-xs shadow-xl border border-white/10">
                  <div className="font-semibold text-white mb-1">{alert.title}</div>
                  <div className="text-slate-300 leading-relaxed">{alert.description}</div>
                </div>
              </div>
            </div>
          )
        })
      )}

      {/* ── Region Name Labels (subtle) ──────────────────────────────── */}
      {MAP_REGIONS.map((region) => {
        const isSelected = selectedRegion === region.id
        return (
          <div
            key={`label-${region.id}`}
            className="absolute pointer-events-none transition-all duration-300"
            style={{
              left: `${region.center[0]}%`,
              top: `${region.center[1]}%`,
              transform: 'translate(-50%, -50%)',
              zIndex: 12,
              opacity: isSelected ? 1 : 0.4,
            }}
          >
            <span
              className="text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md"
              style={{
                color: isSelected ? region.color : '#94A3B8',
                background: isSelected ? `${region.color}15` : 'transparent',
                textShadow: '0 1px 4px rgba(0,0,0,0.8)',
              }}
            >
              {region.shortName}
            </span>
          </div>
        )
      })}

      {/* ── Hover Tooltip ────────────────────────────────────────────── */}
      {hoveredRegion && (
        <div
          className="region-tooltip visible"
          style={{ left: tooltipPos.x, top: tooltipPos.y }}
        >
          <div className="flex items-center gap-2">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: MAP_REGIONS.find((r) => r.id === hoveredRegion)?.color }}
            />
            {MAP_REGIONS.find((r) => r.id === hoveredRegion)?.shortName}
          </div>
          <div className="text-[10px] text-slate-400 font-normal mt-0.5">
            Click to select region
          </div>
        </div>
      )}

      {/* ── Region label (top center) ────────────────────────────────── */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 z-20">
        <div className="glass-card rounded-xl px-6 py-3 flex items-center gap-3">
          <div
            className="w-2.5 h-2.5 rounded-full animate-pulse"
            style={{ background: MAP_REGIONS.find((r) => r.id === selectedRegion)?.color || '#10B981' }}
          />
          <span className="text-sm font-semibold text-white tracking-wide">
            {MAP_REGIONS.find((r) => r.id === selectedRegion)?.shortName || 'Selected Region'}
          </span>
          <span className="text-xs text-slate-400 ml-2">
            {rc ? `${rc.center[1].toFixed(1)}°N, ${Math.abs(rc.center[0]).toFixed(1)}°${rc.center[0] > 0 ? 'E' : 'W'}` : ''}
          </span>
        </div>
      </div>

      {/* Coordinates display (bottom left) */}
      <div className="absolute bottom-4 left-4 z-20 glass-card rounded-lg px-3 py-2 text-xs font-mono text-slate-300">
        <span className="text-accent">LAT</span> {rc ? rc.center[1].toFixed(4) : '0.0000'}° &nbsp;
        <span className="text-accent">LON</span> {rc ? rc.center[0].toFixed(4) : '0.0000'}° &nbsp;
        <span className="text-accent">Z</span> {rc ? rc.zoom : 6}
      </div>

      {/* Satellite info (bottom right) */}
      <div className="absolute bottom-4 right-4 z-20 glass-card rounded-lg px-3 py-2 text-xs text-slate-400">
        Sentinel-2 MSI · 10m resolution · Last pass: 2h ago
      </div>
    </div>
  )
}
