'use client'

/**
 * AlertMarkerLayer — manages alert markers on a MapLibre map.
 * Follows the same imperative pattern as RegionLayer.
 * Reads selectedRegion, selectedDate, and layerVisibility from Zustand.
 * Supports severity colors, hover effects, rich popups with timestamp/confidence/status.
 */

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { listAlerts } from '@/lib/alertsApi'

interface AlertMarkerLayerProps {
  map: any
  mapLib: any
}

function formatTimestamp(ts: string): string {
  if (!ts) return ''
  const date = new Date(ts)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const severityConfig = {
  critical: { color: '#EF4444', label: 'CRITICAL', glow: 'rgba(239, 68, 68, 0.6)' },
  warning: { color: '#F59E0B', label: 'WARNING', glow: 'rgba(245, 158, 11, 0.6)' },
  info: { color: '#3B82F6', label: 'INFO', glow: 'rgba(59, 130, 246, 0.6)' }
}

const statusConfig = {
  active: { bg: 'rgba(34, 197, 94, 0.2)', text: '#4ade80' },
  monitoring: { bg: 'rgba(245, 158, 11, 0.2)', text: '#fbbf24' },
  resolved: { bg: 'rgba(148, 163, 184, 0.2)', text: '#94a3b8' }
}

export default function AlertMarkerLayer({ map, mapLib }: AlertMarkerLayerProps) {
  const markersRef = useRef<any[]>([])
  const { selectedRegion, layerVisibility } = useAppStore()
  const alertLayerState = layerVisibility['alert-markers']

  useEffect(() => {
    if (!map || !mapLib) return

    // Clear existing markers
    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []

    // Check visibility
    if (!alertLayerState?.visible) return

    let cancelled = false
    const opacity = alertLayerState?.opacity ?? 1

    listAlerts().then((response) => {
      if (cancelled) return
      const alerts = response.alerts.filter((alert) => !alert.region_id || alert.region_id === selectedRegion)

      alerts.forEach((alert: any) => {
        // Determine severity
        const severity = alert.severity || 'info'
        const { color, label, glow } = severityConfig[severity as keyof typeof severityConfig] || severityConfig.info

        const statusStr = alert.status || 'monitoring'
        const statusStyle = statusConfig[statusStr as keyof typeof statusConfig] || statusConfig.monitoring

        // Create marker element
        const el = document.createElement('div')
        el.className = 'alert-marker-enhanced'

        el.style.width = '18px'
        el.style.height = '18px'
        el.style.backgroundColor = color
        el.style.borderRadius = '50%'
        el.style.border = '2px solid rgba(255,255,255,0.8)'
        el.style.boxShadow = `0 0 10px 2px ${glow}`
        el.style.cursor = 'pointer'
        el.style.opacity = opacity.toString()
        el.style.transition = 'transform 0.2s ease, box-shadow 0.2s ease'

        // Optional: you could add an animation class here if defined in global CSS
        // el.style.animation = 'pulse-marker 2s infinite'

        el.addEventListener('mouseenter', () => {
          el.style.transform = 'scale(1.3)'
          el.style.boxShadow = `0 0 15px 4px ${glow}`
        })
        el.addEventListener('mouseleave', () => {
          el.style.transform = 'scale(1)'
          el.style.boxShadow = `0 0 10px 2px ${glow}`
        })

        // Create popup HTML
        const popupHtml = `
<div style="font-family:Inter,sans-serif;padding:8px 4px;max-width:260px;">
  <!-- Severity badge -->
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
    <span style="background-color:${color};color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;letter-spacing:0.5px;">${label}</span>
    <span style="background-color:${statusStyle.bg};color:${statusStyle.text};padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;text-transform:uppercase;">${statusStr}</span>
  </div>
  <!-- Title -->
  <div style="font-weight:600;font-size:13px;margin-bottom:4px;color:#fff;">${alert.message || 'Alert'}</div>
  <!-- Description -->
  <div style="font-size:12px;color:#94a3b8;line-height:1.5;margin-bottom:8px;">${alert.is_read ? 'Read' : 'Active alert'}</div>
  <!-- Metadata row -->
  <div style="display:flex;gap:12px;font-size:11px;color:#64748b;border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;">
    <span>🕐 ${formatTimestamp(alert.created_at)}</span>
    <span>${alert.is_read ? 'READ' : 'UNREAD'}</span>
  </div>
</div>
      `

        // Create popup
        const popup = new mapLib.Popup({
          offset: 12,
          className: 'tt-popup',
          closeButton: false
        }).setHTML(popupHtml)

        const coords = alert.coordinates
        if (!coords) return

        // Add to map
        const marker = new mapLib.Marker({ element: el })
          .setLngLat([coords[0], coords[1]])
          .setPopup(popup)
          .addTo(map)

        // Push to markersRef
        markersRef.current.push(marker)
      })
    }).catch(() => {
      // The dashboard alert panel surfaces backend failures to the user.
    })

    return () => {
      cancelled = true
      // eslint-disable-next-line react-hooks/exhaustive-deps
      markersRef.current.forEach((m) => m.remove())
      markersRef.current = []
    }
  }, [map, mapLib, selectedRegion, alertLayerState?.visible, alertLayerState?.opacity])

  return null
}
