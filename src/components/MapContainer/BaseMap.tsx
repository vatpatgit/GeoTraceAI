'use client'

import { useRef, useEffect, useState, useCallback } from 'react'
import { format, parseISO } from 'date-fns'
import { useAppStore } from '@/store/useAppStore'
import { REGION_CENTERS, getRecentAlerts, MAP_REGIONS } from '@/lib/mockData'
import type { MapRegion } from '@/lib/mockData'
import { loadMapLibrary } from '@/services/maps/mapProvider'
import { createUnifiedMapStyle, MAP_LAYERS } from '@/services/maps/mapStyle'
import RegionLayer from './layers/RegionLayer'
import AlertMarkerLayer from './layers/AlertMarkerLayer'
import SentinelImageryLayer, { type SentinelImageryStatus } from './layers/SentinelImageryLayer'
import ChangeDetectionLayer from './layers/ChangeDetectionLayer'
import ViewModeSwitcher from './ViewModeSwitcher'
import MapControls from './MapControls'

// ─── BaseMap Component ────────────────────────────────────────────────────────
export default function BaseMap() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<any>(null)
  const mapLibRef = useRef<any>(null)         // holds the dynamically-imported GL library
  const [mapLoaded, setMapLoaded] = useState(false)
  const [mapError, setMapError] = useState(false)
  const [mapInitializing, setMapInitializing] = useState(true)
  const [sentinelStatus, setSentinelStatus] = useState<SentinelImageryStatus>({ state: 'idle' })
  const [cursorCoords, setCursorCoords] = useState<{ lng: number; lat: number } | null>(null)
  const { mapView, updateMapCenter, updateZoom, setMapView, selectedRegion, regions, setClickedPoint } = useAppStore()

  const currentViewMode = mapView.viewMode || 'globe'

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
          style: createUnifiedMapStyle(),
          center: mapView.center,
          zoom: mapView.zoom,
          pitch: currentViewMode === 'globe' ? 10 : 0,
          bearing: 0,
          attributionControl: true,
        })

        map.current = mapInstance

        mapInstance.on('load', () => {
          if (!cancelled) {
            try {
              if (currentViewMode === 'globe') {
                mapInstance.setProjection({ type: 'globe' })
              } else {
                mapInstance.setProjection({ type: 'mercator' })
              }
            } catch (err) {
              console.warn('Projection initialization notice:', err)
            }
            setMapLoaded(true)
            setMapInitializing(false)
          }
        })

        mapInstance.on('error', () => {
          if (!cancelled && !map.current) {
            setMapError(true)
            setMapInitializing(false)
          }
        })

        mapInstance.on('mousemove', (e: any) => {
          setCursorCoords({
            lng: Number(e.lngLat.lng.toFixed(4)),
            lat: Number(e.lngLat.lat.toFixed(4)),
          })
        })

        mapInstance.on('click', (e: any) => {
          const lng = Number(e.lngLat.lng.toFixed(4))
          const lat = Number(e.lngLat.lat.toFixed(4))
          setClickedPoint({
            lon: lng,
            lat,
            confidence: 0.88,
          })
        })

        mapInstance.on('moveend', () => {
          if (!map.current) return
          const center = map.current.getCenter()
          const zoom = map.current.getZoom()
          const pitch = map.current.getPitch()
          const bearing = map.current.getBearing()
          updateMapCenter([center.lng, center.lat])
          updateZoom(zoom)
          setMapView({ pitch, bearing })
        })
      } catch {
        if (!cancelled) {
          setMapError(true)
          setMapInitializing(false)
        }
      }
    }

    initMap()

    // Cleanup: remove map instance on unmount / hot-reload
    return () => {
      cancelled = true
      if (map.current) {
        map.current.remove()
        map.current = null
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Handle View Mode changes (Globe vs Satellite vs Map) smoothly on the same map instance
  useEffect(() => {
    if (!map.current || !mapLoaded) return

    const m = map.current

    try {
      if (currentViewMode === 'globe') {
        m.setProjection({ type: 'globe' })

        if (m.getLayer(MAP_LAYERS.SATELLITE)) {
          m.setLayoutProperty(MAP_LAYERS.SATELLITE, 'visibility', 'visible')
        }
        if (m.getLayer(MAP_LAYERS.MAP)) {
          m.setLayoutProperty(MAP_LAYERS.MAP, 'visibility', 'none')
        }

        m.easeTo({
          pitch: Math.min(m.getPitch() || 15, 30),
          duration: 1000,
          essential: true,
        })
      } else if (currentViewMode === 'satellite') {
        m.setProjection({ type: 'mercator' })

        if (m.getLayer(MAP_LAYERS.SATELLITE)) {
          m.setLayoutProperty(MAP_LAYERS.SATELLITE, 'visibility', 'visible')
        }
        if (m.getLayer(MAP_LAYERS.MAP)) {
          m.setLayoutProperty(MAP_LAYERS.MAP, 'visibility', 'none')
        }

        m.easeTo({
          pitch: 0,
          bearing: 0,
          duration: 1000,
          essential: true,
        })
      } else if (currentViewMode === 'map') {
        m.setProjection({ type: 'mercator' })

        if (m.getLayer(MAP_LAYERS.MAP)) {
          m.setLayoutProperty(MAP_LAYERS.MAP, 'visibility', 'visible')
        }
        if (m.getLayer(MAP_LAYERS.SATELLITE)) {
          m.setLayoutProperty(MAP_LAYERS.SATELLITE, 'visibility', 'none')
        }

        m.easeTo({
          pitch: 0,
          bearing: 0,
          duration: 1000,
          essential: true,
        })
      }
    } catch (err) {
      console.warn('Error adjusting view mode projection/layers:', err)
    }
  }, [currentViewMode, mapLoaded])

  // Fly to region when selected region changes
  useEffect(() => {
    const region = regions.find((item) => item.id === selectedRegion)
    if (!region) return
    const center: [number, number] = [(region.bbox.minLon + region.bbox.maxLon) / 2, (region.bbox.minLat + region.bbox.maxLat) / 2]

    if (map.current && mapLoaded) {
      map.current.flyTo({
        center,
        zoom: currentViewMode === 'globe' ? 4.5 : 5,
        duration: 2000,
        essential: true,
      })
    }
  }, [selectedRegion, regions, mapLoaded, currentViewMode])

  const handleResetView = () => {
    if (map.current && mapLoaded) {
      map.current.flyTo({
        center: [-65.0, -2.5],
        zoom: currentViewMode === 'globe' ? 2 : 4,
        pitch: currentViewMode === 'globe' ? 15 : 0,
        bearing: 0,
        duration: 1800,
        essential: true,
      })
    }
  }

  // Alert markers are now managed by AlertMarkerLayer

  // Fallback: enhanced interactive mock map
  if (mapError) {
    return <InteractiveMap />
  }

  const activeRegion = regions.find((r) => r.id === selectedRegion)

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#050811]" style={{ minHeight: '400px' }}>
      {/* Loading skeleton — themed spinner while map downloads tiles */}
      {mapInitializing && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-[#050811]">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 border-2 border-[#33E1FF]/30 border-t-[#33E1FF] rounded-full animate-spin" />
            <span className="text-sm text-slate-300 font-medium tracking-wide">
              Initializing Earth visualization...
            </span>
          </div>
        </div>
      )}

      {/* MapLibre WebGL container */}
      <div ref={mapContainer} className="w-full h-full relative z-10" style={{ minHeight: '400px' }} />

      {/* Top Right: View Mode Switcher */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-3">
        <ViewModeSwitcher />
      </div>

      {/* Right Side: Map Navigation Controls */}
      <div className="absolute top-20 right-4 z-20">
        <MapControls map={map.current} onReset={handleResetView} />
      </div>

      {/* Region & data overlays */}
      {mapLoaded && map.current && mapLibRef.current && (
        <>
          <SentinelImageryLayer
            map={map.current}
            regions={regions}
            onStatusChange={setSentinelStatus}
          />
          <ChangeDetectionLayer map={map.current} mapLib={mapLibRef.current} />
          <RegionLayer map={map.current} mapLib={mapLibRef.current} regions={regions} />
          <AlertMarkerLayer map={map.current} mapLib={mapLibRef.current} />
        </>
      )}

      {/* Sentinel Status Notifications */}
      {sentinelStatus.state === 'loading' && !mapInitializing && (
        <div className="absolute top-16 right-4 z-20 glass-card rounded-lg px-3 py-2 text-xs text-slate-300 flex items-center gap-2 border border-white/10 shadow-lg">
          <div className="w-3 h-3 border border-[#33E1FF]/40 border-t-[#33E1FF] rounded-full animate-spin" />
          Loading Sentinel-2 imagery...
        </div>
      )}
      {sentinelStatus.state === 'error' && (
        <div className="absolute top-16 right-4 z-20 glass-card rounded-lg px-3 py-2 text-xs text-amber-300 max-w-xs border border-amber-500/20 shadow-lg">
          Sentinel-2 unavailable • Using base imagery
        </div>
      )}
      {sentinelStatus.state === 'loaded' && (
        <div className="absolute bottom-4 right-4 z-20 glass-card rounded-lg px-3 py-1.5 text-xs text-slate-400 border border-white/10">
          Sentinel-2 • {format(parseISO(sentinelStatus.date), 'd MMM yyyy')}
        </div>
      )}

      {/* Dynamic HUD: Coordinates & View status (bottom left) */}
      <div className="absolute bottom-4 left-4 z-20 flex items-center gap-2 glass-card rounded-lg px-3 py-2 text-xs font-mono text-slate-300 border border-white/10 select-none">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#33E1FF] animate-pulse" />
          <span className="text-[#33E1FF] font-semibold uppercase">{currentViewMode.toUpperCase()}</span>
        </div>
        <span className="text-slate-600">|</span>
        <span>
          LAT {cursorCoords ? cursorCoords.lat : (mapView.center[1] || 0).toFixed(4)}°
        </span>
        <span>
          LON {cursorCoords ? cursorCoords.lng : (mapView.center[0] || 0).toFixed(4)}°
        </span>
        <span className="text-slate-600">|</span>
        <span>Z {(mapView.zoom || 0).toFixed(1)}</span>
        {activeRegion && (
          <>
            <span className="text-slate-600">|</span>
            <span className="text-slate-200 font-sans font-medium">{activeRegion.name}</span>
          </>
        )}
      </div>
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
