# TerraTrack Component Implementation Guide
## Quick Reference for Building UI Improvements

---

## PART 1: VISUAL MOCKUPS & WIREFRAMES

### Dashboard Layout Evolution

#### Current Layout (Already Built)
```
┌──────────────────────────────────────────────────────────┐
│              HEADER (Search, Notifications, etc)         │
├──────┬──────────────────────────────────────────────────┤
│      │                                                   │
│ SIDE │                                                   │
│ BAR  │            MAP VIEWER (Canvas-based)             │
│ (w64)│            - Region selector (floating)          │
│      │            - Layer toggle (floating)             │
│  [+] │            - Drawing controls (floating)         │
│      │                                                   │
│      ├─────────────────────────────────────────────────┤
│      │          TIME SLIDER & CONTROLS                  │ (Collapsible)
├──────┴────────────────────────────────────────────────┬─┤
│                                                        │ │
│              MAP AREA (continued)                      │A│
│                                                        │N│
│                                                        │A│
│                                                        │L│
│                                                        │Y│
│                                                        │T│
│                                                        │I│
│                                                        │C│
│                                                        │S│
│                                                        │ │
│                                                        │(w96)
│                                                        │
└────────────────────────────────────────────────────────┴─┘

Legend:
- [+] = Hamburger menu opens sidebar
- ANALYTICS on right = Hidden on mobile (hidden: lg:block)
```

#### Recommended Enhanced Layout (Phase 1+)
```
┌──────────────────────────────────────────────────────────────────┐
│  [≡] │ TerraTrack │ [Search Box] │ [Notifications] [User] [⚙]  │
├──────┬───────────────────────────────────────────┬──────────────┤
│      │  Breadcrumbs: Dashboard > Amazon > North  │              │
│ SIDE │                                           │              │
│ BAR  │           MAPBOX GL MAP                   │ ANALYTICS    │
│      │  ┌─────────────────────────────────────┐  │ PANEL        │
│  -   │  │ [Z+] [Z-]  ╔═══════════════════╗   │  │ (Resizable)  │
│      │  │ [↗] [Full] ║ LEGEND            ║   │  │              │
│  [•] │  │ [🎯] [⊕]   ║ Satellite         ║   │  │ Metrics:     │
│      │  │       [📡]  ║ Change Mask ███  ║   │  │ ┌──────────┐ │
│      │  │       [🎲]  ║ Confidence ▓▓▓▓▓ ║   │  │ │ Δ Area   │ │
│ [→] │  │       [✏]   ║ Alerts    ●●●●● ║   │  │ │ 23.5 km²│ │
│      │  │              ╚═══════════════════╝   │  │ └──────────┘ │
│      │  │            [Split View] [Compare]   │  │              │
│      │  │                                      │  │ Charts:      │
│      │  └─────────────────────────────────────┘  │ [Area Over   │
│      │                                           │  Time]       │
├──────┼───────────────────────────────────────────┼──────────────┤
│      │  [◄ Prev] [Play/Pause] [Speed: 1x] [►]  │              │
│      │  2024-01-01 [═════●］ 2024-01-30        │ [Scroll]     │
│      │  [Last 30d] [Last 90d] [Custom ▼]       │              │
├──────┼───────────────────────────────────────────┼──────────────┤
│      │ [Region Selector] [Layer Toggle]         │              │
│      │ [Filter Chips: Type: All ✕] [+ Add]     │ [⬇ Export]  │
└──────┴───────────────────────────────────────────┴──────────────┘

Controls Legend:
[Z+] = Zoom in
[Z-] = Zoom out
[↗] = Pan/navigate
[Full] = Fullscreen
[🎯] = Reset to default
[⊕] = Measure distance
[📡] = Basemap switcher
[🎲] = Toggle drawing
[✏] = Edit drawn region
[→] = Collapse sidebar
[≡] = Hamburger menu (mobile)
[•] = Active notifications
[Compare] = Split-screen comparison
```

#### Mobile Layout (XS/SM Breakpoint)
```
┌────────────────────────────┐
│ [≡] TT │ Search │ [🔔][👤] │
├────────────────────────────┤
│                            │
│                            │
│         MAP VIEWER         │
│      (Full width)          │
│  [Z] [Z] [Full]            │
│      (Floating)            │
│                            │
│                            │
└────────────────────────────┘
┌────────────────────────────┐
│ [◄] [Play] [Speed] [►]    │
│ [═════●═════]             │
│ Date Range Picker ▼       │
└────────────────────────────┘
┌────────────────────────────┐
│ ⬆ Swipe up to see          │
│ ANALYTICS (Bottom Sheet)   │
│                            │
│ Metrics & Charts           │
│ (Scrollable)               │
│                            │
└────────────────────────────┘

Interactions:
- Swipe up = Show analytics
- Swipe down = Hide analytics
- Pinch = Zoom map
- Two-finger tap = Center
- Landscape = Side-by-side map + mini-chart
```

---

### Sidebar v2 Mockup (Collapsible)

#### Expanded (Default on Desktop)
```
┌──────────────────┐
│ TerraTrack (Logo)│ ← Title
│ AI Satellite Mon │ ← Subtitle (shrinks on collapse)
├──────────────────┤
│                  │
│ [>] Dashboard    │ ← Active indicator (left border)
│ [ ] Regions      │
│ [ ] Analytics    │
│ [ ] Alerts       │ 🔴 (Badge: 3 active alerts)
│ [ ] Reports      │
│ [ ] Settings     │
│                  │
├──────────────────┤
│ User: John Doe   │ ← Footer (profile)
│ Researcher Role  │
│ [Logout]         │
└──────────────────┘
```

#### Collapsed (Icon Only)
```
┌──┐
│TT│ ← Initials/logo only
├──┤
│◆│ ← Active item indicator
│⊞│
│━│
│🔔│ 🔴 ← Badge sticks
│⊞│
│⚙│
│  │
├──┤
│👤│ ← User avatar
│DS│ ← Initials
└──┘
```

#### Mobile (Hidden by Default)
```
Hamburger appears in header when sidebar hidden
┌─────────────────────┐
│ [≡]  TerraTrack     │  ← Hamburger button
├─────────────────────┤
│ › Dashboard         │
│ › Regions           │
│ › Analytics         │
│ › Alerts      [🔴3] │
│ › Reports           │
│ › Settings          │
│ ────────────────    │
│ John Doe            │
│ Researcher          │
│ [Logout]            │
└─────────────────────┘
```

---

### Map Legend Component (Dynamic)

#### Example 1: Change Mask Active
```
╔════════════════════════════╗
║  LEGEND (Draggable)    [×] ║
╠════════════════════════════╣
║ ☑ Satellite                ║
║   (Base map imagery)       ║
║                            ║
║ ☑ Change Mask              ║
║   ████ Deforestation       ║
║        (45% of changes)    ║
║   ████ Wildfire            ║
║        (25% of changes)    ║
║   ████ Urban Expansion     ║
║        (20% of changes)    ║
║   ████ Water Changes       ║
║        (10% of changes)    ║
║                            ║
║ ☐ Confidence Heatmap       ║
║   (Toggle to show)         ║
║                            ║
║ ☐ Alerts                   ║
║   ● Critical               ║
║   ● Warning                ║
║   ● Info                   ║
│                            │
│ Data from: Sentinel-2      │
│ Last updated: Today 2h ago │
╚════════════════════════════╝
```

#### Example 2: Confidence Heatmap Active
```
╔════════════════════════════╗
║  LEGEND                [×] ║
╠════════════════════════════╣
║ ☑ Satellite                ║
║                            ║
║ ☐ Change Mask              ║
║                            ║
║ ☑ Confidence Heatmap       ║
║   Low    ███ High          ║
║    0%              100%    ║
║                            ║
║   Shows data quality.      ║
║   Dark = fully confident   ║
║   in detection.            ║
║                            ║
│ More about confidence »    │
╚════════════════════════════╝
```

---

### Analytics Panel v2 Mockup

#### Current (Simple) vs. Enhanced (Recommended)

**Current:**
```
┌──────────────────────────┐
│  × ANALYTICS    [↕] [↔] │
├──────────────────────────┤
│ Area Monitored           │
│ 523.5 km²                │
│                          │
│ Changes (30d)            │
│ 12.5 km²   ↑ 15%        │
│                          │
│ Changes (90d)            │
│ 14.2 km²                 │
│                          │
│ Avg Confidence           │
│ 87%                      │
│                          │
│ Active Alerts            │
│ 3                        │
│                          │
│ Time Series Chart        │
│ [Line chart]             │
└──────────────────────────┘
```

**Recommended (Enhanced):**
```
┌────────────────────────────────────┐
│  ANALYTICS[∧] [Metrics][Charts]    │ ← Tabs
├────────────────────────────────────┤
│                                    │
│  ┌──────────┐  ┌──────────┐       │
│  │ 23.5 km² │  │ 89% Conf │       │
│  │ Area     │  │ Quality  │ ← Metric Cards
│  │ Change   │  │          │    (Expandable)
│  └──────────┘  └──────────┘       │
│                                    │
│  ┌──────────┐  ┌──────────┐       │
│  │  +15%    │  │ 3 Alert  │       │
│  │ Trend    │  │ Active   │       │
│  │ (30 day) │  │          │       │
│  └──────────┘  └──────────┘       │
│                                    │
│  STATISTICAL SUMMARY               │
│  Min: 0.5 km²       Max: 56.2 km² │
│  Avg: 12.3 km²      Std: 5.2 km²  │
│                                    │
│  CHANGE TYPE BREAKDOWN             │
│  [Pie Chart]                       │ ← Interactive
│  • Deforestation 45%               │
│  • Wildfire 25%                    │
│  • Urban 20%                       │
│  • Other 10%                       │
│                                    │
│  COMPARISON WITH OTHER REGIONS     │
│  ☑ Amazon North (this)            │
│  ☐ Amazon South                    │
│  ☐ Cerrado                         │
│  [Compare]                         │
│                                    │
│  [⬇ Export as CSV] [⬇ Export PDF] │
└────────────────────────────────────┘
```

---

### Alert Panel Mockup (New Component)

#### Persistent Alert Panel (Collapsible)

**Expanded:**
```
┌─ ACTIVE ALERTS (3) [−] ┐
├────────────────────────┤
│ [🔴 CRITICAL]          │ ← Severity badge
│ Wildfire Detected      │
│ Amazon North Sector    │
│ Area: 5.2 km²          │
│ Confidence: 78%        │
│ at 14:32 today         │
│ [Details] [Dismiss]    │
├────────────────────────┤
│ [🟠 WARNING]           │
│ Deforestation Rate ↑   │
│ Amazon Central         │
│ +23% vs last month     │
│ at 10:15 today         │
│ [Details] [Snooze 1h]  │
├────────────────────────┤
│ [🔵 INFO]              │
│ Data Update Available  │
│ New satellite imagery  │
│ available for region   │
│ [Details] [Dismiss]    │
├────────────────────────┤
│ [History] [Settings]   │
└────────────────────────┘
```

**Collapsed:**
```
┌─ ALERTS [+] ┐
│ 🔴 3        │ ← Count badge
└─────────────┘
```

#### Toast Notification (Temporary)
```
Position: Top-right, above all layers

┌─────────────────────────────────┐
│ 🔔 New Alert: Wildfire Detected │
│    Amazon North - 5.2 km²    [×]│
│    [View] [Dismiss] [Snooze 1h] │
└─────────────────────────────────┘

Auto-dismiss after 8 seconds unless interacted
```

---

### Comparison Mode Split-Screen

```
┌─────────────────────────────────────────────┐
│  Comparison Mode    [Close]                 │
│  Amazon North: 2024-06-15 vs. 2024-12-15   │
├──────────────────┬──────────────────────────┤
│                  │                          │
│  JUNE 2024       │  DECEMBER 2024           │
│                  │                          │
│  [Z] [Pan]       │  [Z] [Pan]               │
│                  │                          │
│  ┌──────────────┐│┌──────────────────────┐ │
│  │              ││                       │ │
│  │  Map View 1  ││  Map View 2           │ │
│  │  (Synced     ││  (Synced             │ │
│  │   zoom)      ││   zoom)              │ │
│  │              ││                       │ │
│  │  Red areas:  ││  Red areas:          │ │
│  │  Deforest    ││  Deforest            │ │
│  │              ││                       │ │
│  └──────────────┘│└──────────────────────┘ │
│                  │                          │
│  12.5 km²        │  14.2 km²               │
│  Change Area     │  Change Area            │
│                  │                          │
│  89% Conf        │  87% Conf               │
│                  │                          │
├──────────────────┴──────────────────────────┤
│ Analysis: +13% increase over 6 months       │
│ Slider: [════════●──────]                   │
│ Opacity: Adjust overlay transparency        │
└──────────────────────────────────────────────┘
```

---

### Search & Filter UI

#### Search Bar (Enhanced)
```
Current:
┌────────────────────────────────────┐
│ 🔍 Search regions, alerts...       │
└────────────────────────────────────┘

Enhanced:
┌────────────────────────────────────┐
│ 🔍 Search regions, dates, alerts...|
│                               [×]  │
├────────────────────────────────────┤
│                                    │
│ RECENT SEARCHES                    │
│ · Amazon Basin North               │
│ · Cerrado Deforestation            │
│ · California Wildfire Risk         │
│                                    │
│ TRENDING                           │
│ • Amazon Basin (15 views)          │
│ • Deforestation (12 views)         │
│                                    │
│ SEARCH RESULTS                     │
│ Regions                            │
│ ├ Amazon - Northern Sector         │
│ ├ Amazon - Central Sector          │
│ └ Amazon - Southern Sector         │
│                                    │
│ Dates                              │
│ ├ 2024-01-01 to 2024-01-30         │
│ ├ 2024-02-01 to 2024-02-29         │
│                                    │
│ Alerts                             │
│ ├ Wildfire Detected (5.2 km²)      │
│ ├ Deforestation Rate ↑             │
│                                    │
│ [See all results]                  │
└────────────────────────────────────┘
```

#### Filter Chips
```
┌──────────────────────────────────────────────┐
│ Change Type: All ✕ │ Severity: All ✕        │
│ ┌────────────────┬──────────┬──────────────┐ │
│ │ All | Deforest │ Wildfire │ + Add Filter │ │
│ └────────────────┴──────────┴──────────────┘ │
│                                              │
│ Confidence: 70% - 100% ✕                     │
│ ├────────────────────────────────────────┤  │
│ │●                                    ●●● │  │
│ │0%                                    100%│
│ │                                         │  │
│ (Slider to adjust range)                    │
│                                              │
│ [Clear All] [Apply]                         │
└──────────────────────────────────────────────┘
```

---

## PART 2: COMPONENT IMPLEMENTATION TEMPLATES

### 1. BaseMap Component (Mapbox GL Integration)

```typescript
// src/components/MapContainer/BaseMap.tsx
'use client'

import { useRef, useEffect, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import { useAppStore } from '@/store/useAppStore'
import 'mapbox-gl/dist/mapbox-gl.css'

interface BaseMapProps {
  accessToken: string
  sentinelHubToken: string
}

export default function BaseMap({ accessToken, sentinelHubToken }: BaseMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<mapboxgl.Map | null>(null)
  const { mapView, updateMapCenter, updateZoom, baseMapStyle, setBaseMapStyle } = useAppStore()

  useEffect(() => {
    if (!mapContainer.current) return

    mapboxgl.accessToken = accessToken

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: `mapbox://styles/mapbox/${baseMapStyle}-v12`,
      center: mapView.center,
      zoom: mapView.zoom,
      pitch: 0,
    })

    // Add Sentinel-2 satellite tiles as an additional layer
    map.current.on('load', () => {
      // Add Sentinel Hub WMS source
      map.current?.addSource('sentinel-tiles', {
        type: 'raster',
        url: `https://services.sentinel-hub.com/wcs?SERVICE=WCS&REQUEST=GetCoverage&COVERAGEID=S2L2A&FORMAT=image/jpeg`,
        tileSize: 256,
      })

      // Add satellite layer
      map.current?.addLayer({
        id: 'satellite-tiles',
        type: 'raster',
        source: 'sentinel-tiles',
        paint: { 'raster-opacity': 0.85 },
      })
    })

    // Handle map interactions
    map.current.on('move', () => {
      if (map.current) {
        const center = map.current.getCenter()
        const zoom = map.current.getZoom()
        updateMapCenter([center.lng, center.lat])
        updateZoom(zoom)
      }
    })

    return () => {
      map.current?.remove()
    }
  }, [accessToken, sentinelHubToken])

  return <div ref={mapContainer} className="w-full h-full" />
}
```

---

### 2. MapLegend Component

```typescript
// src/components/MapContainer/MapLegend.tsx
'use client'

import { useState } from 'react'
import { X, GripHorizontal } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'

const legendItems = {
  satellite: {
    label: 'Satellite',
    description: 'Base map imagery',
    color: null,
  },
  changeMask: {
    label: 'Change Mask',
    items: [
      { label: 'Deforestation', color: '#DC2626', percent: 45 },
      { label: 'Wildfire', color: '#FF7F00', percent: 25 },
      { label: 'Urban Expansion', color: '#808080', percent: 20 },
      { label: 'Water Changes', color: '#0066CC', percent: 10 },
    ],
  },
  confidence: {
    label: 'Confidence Heatmap',
    description: 'Data quality indicator',
    gradient: ['#FF4444', '#FFAA00', '#00FF00'],
  },
  alerts: {
    label: 'Alerts',
    items: [
      { label: 'Critical', color: '#DC2626' },
      { label: 'Warning', color: '#FF7F00' },
      { label: 'Info', color: '#0EA5E9' },
    ],
  },
}

export default function MapLegend() {
  const [isVisible, setIsVisible] = useState(true)
  const [isDraggable, setIsDraggable] = useState(false)
  const { mapView, toggleLayer } = useAppStore()

  if (!isVisible) {
    return (
      <button
        onClick={() => setIsVisible(true)}
        className="absolute bottom-4 right-4 z-10 p-2 bg-slate-dark rounded border border-slate-600 hover:bg-slate-700"
        aria-label="Show legend"
      >
        Legend
      </button>
    )
  }

  return (
    <div
      className={`absolute top-4 right-4 z-10 bg-slate-dark border border-slate-600 rounded-lg p-4 max-w-xs ${
        isDraggable ? 'cursor-grab' : ''
      }`}
      onMouseDown={() => setIsDraggable(true)}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Legend</h3>
        <div className="flex gap-2">
          <button
            onMouseDown={(e) => {
              e.stopPropagation()
              setIsDraggable(!isDraggable)
            }}
            className="p-1 hover:bg-slate-700 rounded text-slate-400"
          >
            <GripHorizontal className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsVisible(false)}
            className="p-1 hover:bg-slate-700 rounded text-slate-400"
            aria-label="Hide legend"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Legend Items */}
      <div className="space-y-3 text-sm">
        {/* Satellite */}
        {mapView.activeLayers.satellite && (
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={true}
                onChange={() => toggleLayer('satellite')}
                className="w-4 h-4"
              />
              <span className="text-slate-300">Satellite</span>
            </label>
            <p className="text-xs text-slate-400 ml-6">Base map imagery</p>
          </div>
        )}

        {/* Change Mask */}
        {mapView.activeLayers.changeMask && (
          <div>
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={true}
                onChange={() => toggleLayer('changeMask')}
                className="w-4 h-4"
              />
              <span className="text-slate-300">Change Mask</span>
            </label>
            <div className="ml-6 space-y-1">
              {legendItems.changeMask.items.map((item) => (
                <div key={item.label} className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-xs text-slate-400">
                    {item.label} ({item.percent}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Confidence Heatmap */}
        {mapView.activeLayers.confidence && (
          <div>
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={true}
                onChange={() => toggleLayer('confidence')}
                className="w-4 h-4"
              />
              <span className="text-slate-300">Confidence</span>
            </label>
            <div className="ml-6">
              <div className="text-xs text-slate-400 mb-1">Low to High</div>
              <div className="h-3 rounded bg-gradient-to-r from-red-500 via-yellow-500 to-green-500" />
              <div className="flex justify-between text-xs text-slate-400 mt-1">
                <span>0%</span>
                <span>100%</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <hr className="my-3 border-slate-600" />

      {/* Footer */}
      <div className="text-xs text-slate-400">
        <p>Data from: Sentinel-2</p>
        <p>Last updated: Today 2h ago</p>
      </div>
    </div>
  )
}
```

---

### 3. AlertPanel Component (New)

```typescript
// src/components/AlertSystem/AlertPanel.tsx
'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, AlertCircle, AlertTriangle, Info, X } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import type { Alert } from '@/types'

// Mock data - replace with real API
const mockAlerts: Alert[] = [
  {
    id: '1',
    regionId: 'amazon-north',
    date: '2024-03-10T14:32:00Z',
    severity: 'critical',
    message: 'Wildfire Detected',
    coordinates: [-65.0, -2.5],
    affectedArea: 5.2,
    changeType: 'wildfire',
    dismissed: false,
  },
  {
    id: '2',
    regionId: 'amazon-central',
    date: '2024-03-10T10:15:00Z',
    severity: 'warning',
    message: 'Deforestation Rate Increasing',
    coordinates: [-62.5, -5.0],
    affectedArea: 0,
    changeType: 'deforestation',
    dismissed: false,
  },
  {
    id: '3',
    regionId: 'cerrado',
    date: '2024-03-09T16:45:00Z',
    severity: 'info',
    message: 'New Data Available',
    coordinates: [-48.0, -12.0],
    affectedArea: 0,
    changeType: 'data_update',
    dismissed: false,
  },
]

export default function AlertPanel() {
  const [isExpanded, setIsExpanded] = useState(true)
  const [alerts, setAlerts] = useState<Alert[]>(mockAlerts)

  const severityConfig = {
    critical: { color: '#DC2626', icon: AlertCircle, label: 'Critical' },
    warning: { color: '#FF7F00', icon: AlertTriangle, label: 'Warning' },
    info: { color: '#0EA5E9', icon: Info, label: 'Info' },
  }

  const handleDismiss = (alertId: string) => {
    setAlerts(alerts.filter((a) => a.id !== alertId))
  }

  const handleSnooze = (alertId: string, hours: number) => {
    // TODO: Implement snooze logic
    handleDismiss(alertId)
  }

  const activeAlerts = alerts.filter((a) => !a.dismissed).length

  if (!isExpanded) {
    return (
      <div className="absolute bottom-4 left-4 z-20">
        <button
          onClick={() => setIsExpanded(true)}
          className="flex items-center gap-2 px-4 py-2 bg-slate-dark border border-slate-600 rounded-lg hover:bg-slate-700 transition-colors"
          aria-label="Show alerts panel"
        >
          <span className="text-sm font-medium text-slate-300">Alerts</span>
          <span
            className="px-2 py-1 text-xs font-bold rounded"
            style={{ backgroundColor: severityConfig.critical.color + '20', color: severityConfig.critical.color }}
          >
            {activeAlerts}
          </span>
          <ChevronUp className="w-4 h-4 text-slate-400" />
        </button>
      </div>
    )
  }

  return (
    <div className="absolute bottom-4 left-4 z-20 w-96 bg-slate-dark border border-slate-600 rounded-lg shadow-lg overflow-hidden flex flex-col max-h-96">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-600">
        <h3 className="text-sm font-semibold text-slate-300">
          Active Alerts ({activeAlerts})
        </h3>
        <button
          onClick={() => setIsExpanded(false)}
          className="p-1 hover:bg-slate-700 rounded text-slate-400"
          aria-label="Collapse alerts"
        >
          <ChevronDown className="w-4 h-4" />
        </button>
      </div>

      {/* Alert List */}
      <div className="overflow-y-auto flex-1">
        {alerts.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm text-slate-400">No active alerts</p>
          </div>
        ) : (
          <div className="space-y-2 p-3">
            {alerts.map((alert) => {
              const config = severityConfig[alert.severity]
              const Icon = config.icon

              return (
                <div
                  key={alert.id}
                  className="border-l-2 px-3 py-2 rounded bg-slate-700/50 hover:bg-slate-700 transition-colors"
                  style={{ borderColor: config.color }}
                >
                  {/* Header */}
                  <div className="flex items-start gap-2 mb-1">
                    <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: config.color }} />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-slate-200">{alert.message}</div>
                      <div className="text-xs text-slate-400">{alert.coordinates.join(', ')}</div>
                    </div>
                    <button
                      onClick={() => handleDismiss(alert.id)}
                      className="p-1 hover:bg-slate-600 rounded text-slate-400"
                      aria-label="Dismiss alert"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Details */}
                  <div className="text-xs text-slate-300 space-y-0.5">
                    {alert.affectedArea > 0 && <p>Area: {alert.affectedArea.toFixed(1)} km²</p>}
                    <p>
                      {new Date(alert.date).toLocaleString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 mt-2">
                    <button className="text-xs px-2 py-1 bg-slate-600 hover:bg-slate-500 rounded text-slate-300 transition-colors">
                      Details
                    </button>
                    <button
                      onClick={() => handleSnooze(alert.id, 1)}
                      className="text-xs px-2 py-1 bg-slate-600 hover:bg-slate-500 rounded text-slate-300 transition-colors"
                    >
                      Snooze 1h
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="bg-slate-700/50 px-4 py-2 border-t border-slate-600 flex gap-2">
        <button className="flex-1 text-xs px-2 py-1 bg-accent/20 hover:bg-accent/30 rounded text-accent transition-colors">
          History
        </button>
        <button className="flex-1 text-xs px-2 py-1 bg-slate-600 hover:bg-slate-500 rounded text-slate-300 transition-colors">
          Settings
        </button>
      </div>
    </div>
  )
}
```

---

### 4. DateRangePicker Component

```typescript
// src/components/TimeControls/DateRangePicker.tsx
'use client'

import { useState } from 'react'
import { Calendar } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { parseISO, format } from 'date-fns'

const presetRanges = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
  { label: 'Last 6 months', days: 180 },
  { label: 'Last year', days: 365 },
]

export default function DateRangePicker() {
  const { mapView, setDateRange } = useAppStore()
  const [isOpen, setIsOpen] = useState(false)

  const handlePresetSelect = (days: number) => {
    const endDate = new Date()
    const startDate = new Date(endDate)
    startDate.setDate(startDate.getDate() - days)

    setDateRange({
      start: format(startDate, 'yyyy-MM-dd'),
      end: format(endDate, 'yyyy-MM-dd'),
    })
    setIsOpen(false)
  }

  const startDate = mapView.dateRange.start
  const endDate = mapView.dateRange.end

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 bg-slate rounded-lg border border-slate-600 hover:border-accent text-left transition-colors min-w-fit"
        aria-expanded={isOpen}
      >
        <Calendar className="w-4 h-4 text-accent" />
        <span className="text-sm text-slate-300">
          {startDate} to {endDate}
        </span>
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 bg-slate-dark border border-slate-600 rounded-lg p-4 shadow-lg z-20 w-80">
          {/* Presets */}
          <div className="mb-4">
            <h4 className="text-xs font-semibold text-slate-400 mb-2">Quick Select</h4>
            <div className="grid grid-cols-2 gap-2">
              {presetRanges.map((preset) => (
                <button
                  key={preset.days}
                  onClick={() => handlePresetSelect(preset.days)}
                  className="text-xs px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <hr className="border-slate-600 mb-4" />

          {/* Custom Dates */}
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setDateRange({ ...mapView.dateRange, start: e.target.value })}
                className="w-full px-3 py-2 bg-slate rounded border border-slate-600 text-white text-sm focus:outline-none focus:border-accent"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setDateRange({ ...mapView.dateRange, end: e.target.value })}
                className="w-full px-3 py-2 bg-slate rounded border border-slate-600 text-white text-sm focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setIsOpen(false)}
              className="flex-1 px-3 py-2 bg-accent text-background rounded font-medium text-sm hover:bg-accent/90 transition-colors"
            >
              Apply
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="flex-1 px-3 py-2 bg-slate-700 text-slate-300 rounded font-medium text-sm hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
```

---

### 5. MetricsCard Component

```typescript
// src/components/AnalyticsContainer/MetricsCard.tsx
'use client'

import { TrendingUp, TrendingDown } from 'lucide-react'

interface MetricsCardProps {
  label: string
  value: string | number
  unit?: string
  trend?: {
    direction: 'up' | 'down'
    percentage: number
    period: string
  }
  onClick?: () => void
  isExpanded?: boolean
  details?: React.ReactNode
}

export default function MetricsCard({
  label,
  value,
  unit,
  trend,
  onClick,
  isExpanded = false,
  details,
}: MetricsCardProps) {
  const trendColor = trend?.direction === 'up' ? 'text-red-500' : 'text-green-500'
  const TrendIcon = trend?.direction === 'up' ? TrendingUp : TrendingDown

  return (
    <div
      onClick={onClick}
      className={`p-4 rounded-lg border border-slate-600 bg-slate-700/50 hover:bg-slate-700 transition-all cursor-pointer ${
        isExpanded ? 'col-span-2' : ''
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-slate-400 uppercase">{label}</h4>
        {trend && (
          <div className={`flex items-center gap-1 text-xs font-semibold ${trendColor}`}>
            <TrendIcon className="w-3 h-3" />
            <span>{trend.percentage}% {trend.period}</span>
          </div>
        )}
      </div>

      {/* Value */}
      <div className="flex items-baseline gap-1 mb-2">
        <span className="text-2xl font-bold text-slate-100">{value}</span>
        {unit && <span className="text-sm text-slate-400">{unit}</span>}
      </div>

      {/* Details (if expanded) */}
      {isExpanded && details && <div className="mt-4 text-sm text-slate-300">{details}</div>}
    </div>
  )
}
```

---

### 6. Interactive Chart Wrapper

```typescript
// src/components/AnalyticsContainer/InteractiveChart.tsx
'use client'

import { useState } from 'react'
import { Download, Maximize2 } from 'lucide-react'
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

interface InteractiveChartProps {
  data: any[]
  title: string
  type: 'line' | 'area'
  xKey: string
  yKeys: string[]
  onDataPointClick?: (data: any) => void
  onExport?: () => void
}

export default function InteractiveChart({
  data,
  title,
  type,
  xKey,
  yKeys,
  onDataPointClick,
  onExport,
}: InteractiveChartProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  const colors = ['#33E1FF', '#FF7F00', '#10B981', '#DC2626']

  const ChartComponent = type === 'area' ? AreaChart : LineChart
  const DataComponent = type === 'area' ? Area : Line

  return (
    <div className={`border border-slate-600 rounded-lg p-4 bg-slate-700/30 ${isFullscreen ? 'fixed inset-0 z-50' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
        <div className="flex gap-2">
          <button
            onClick={onExport}
            className="p-2 hover:bg-slate-600 rounded text-slate-400 hover:text-slate-200 transition-colors"
            aria-label="Export chart"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-2 hover:bg-slate-600 rounded text-slate-400 hover:text-slate-200 transition-colors"
            aria-label="Toggle fullscreen"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={isFullscreen ? 500 : 300}>
        <ChartComponent
          data={data}
          margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
          onClick={(state) => {
            if (state && state.activeTooltipIndex !== undefined && onDataPointClick) {
              onDataPointClick(data[state.activeTooltipIndex])
            }
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey={xKey} stroke="#6B7280" style={{ fontSize: '12px' }} />
          <YAxis stroke="#6B7280" style={{ fontSize: '12px' }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
            labelStyle={{ color: '#E5E7EB' }}
            cursor={{ fill: 'rgba(51, 225, 255, 0.1)' }}
          />
          <Legend wrapperStyle={{ paddingTop: '10px' }} />
          {yKeys.map((key, index) => (
            <DataComponent
              key={key}
              type="monotone"
              dataKey={key}
              stroke={colors[index % colors.length]}
              fill={colors[index % colors.length]}
              isAnimationActive={true}
            />
          ))}
        </ChartComponent>
      </ResponsiveContainer>
    </div>
  )
}
```

---

## PART 3: STYLING & CSS GUIDELINES

### Glass Morphism Card (Currently Used)

```css
/* Existing in app/globals.css - Enhance it */
.glass-card {
  @apply bg-slate-dark/80 backdrop-blur-md border border-slate-600/30 rounded-lg;
}

.glass-card:hover {
  @apply border-slate-600/60;
}
```

### New Utility Classes to Add

```css
/* src/app/globals.css */

/* Elevation system */
.elevation-1 {
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

.elevation-2 {
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.elevation-3 {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
}

.elevation-glow {
  box-shadow: 0 0 20px rgba(51, 225, 255, 0.3);
}

/* Gradients */
.gradient-accent {
  background: linear-gradient(135deg, #33E1FF 0%, #00A8CC 100%);
}

.gradient-danger {
  background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%);
}

.gradient-success {
  background: linear-gradient(135deg, #10B981 0%, #059669 100%);
}

/* Hover effects */
.hover-lift {
  @apply transition-all duration-300 hover:elevation-3 hover:scale-105;
}

.hover-glow {
  @apply transition-all duration-300 hover:elevation-glow;
}

/* Focus states */
.focus-ring {
  @apply focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background;
}

/* Animations */
@keyframes shimmer {
  0% {
    background-position: -1000px 0;
  }
  100% {
    background-position: 1000px 0;
  }
}

.animate-shimmer {
  animation: shimmer 2s infinite;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.1),
    transparent
  );
  background-size: 1000px 100%;
}

@keyframes pulse-ring {
  0% {
    box-shadow: 0 0 0 0 rgba(51, 225, 255, 0.7);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(51, 225, 255, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(51, 225, 255, 0);
  }
}

.animate-pulse-ring {
  animation: pulse-ring 2s infinite;
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #374151;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #4B5563;
}
```

---

## Implementation Priority Matrix

| Component | Priority | Complexity | Est. Hours | Dependencies |
|-----------|----------|------------|-----------|--------------|
| MapLegend | P0 (Day 1) | Low | 2 | BaseMap |
| AlertPanel | P0 (Day 2) | Low | 2 | useAppStore |
| DateRangePicker | P0 (Day 2) | Low | 3 | useAppStore |
| BaseMap (Mapbox) | P1 (Week 1) | High | 8 | Mapbox token |
| MetricsCard | P1 (Week 1) | Low | 2 | NA |
| InteractiveChart | P1 (Week 1) | Medium | 4 | Recharts |
| CollapsibleSidebar | P2 (Week 2) | Medium | 3 | useAppStore |
| ComparisonView | P2 (Week 2) | High | 6 | BaseMap |
| DrawingTool | P2 (Week 2) | High | 6 | Mapbox |
| ReportBuilder | P3 (Week 3) | Medium | 5 | PDF.js |

---

## Quick Start Checklist for Developer

- [ ] Install Mapbox GL and types: `npm install mapbox-gl`
- [ ] Get Mapbox access token from dashboard
- [ ] Get Sentinel Hub API credentials
- [ ] Update `useAppStore` with new state fields from Part 1
- [ ] Add new types to `types/index.ts`
- [ ] Create `MapContainer/` folder in components
- [ ] Start with BaseMap component implementation
- [ ] Connect AlertPanel to real alert data from backend
- [ ] Test responsive design on mobile devices
- [ ] Set up Storybook for component showcase

---

**Document Status**: Ready for development  
**Last Updated**: March 2026  
**Suggested Start**: Begin with Part 1 (Phase 1 implementation)
