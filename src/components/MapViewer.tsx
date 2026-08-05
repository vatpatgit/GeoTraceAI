'use client'

import { useRef, useEffect, useState, useCallback } from 'react'
import { ZoomIn, ZoomOut, Download, Layers, X } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { getConfidenceAtPoint, getOverlayUrl } from '@/lib/mockApi'
import { motion, AnimatePresence } from 'framer-motion'

export default function MapViewer() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState<[number, number] | null>(null)
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([])
  const [tooltip, setTooltip] = useState<{
    x: number
    y: number
    confidence: number
  } | null>(null)

  const {
    mapView,
    updateMapCenter,
    updateZoom,
    isDrawing,
    setIsDrawing,
    setDrawnPolygon,
    toggleComparisonMode,
    setClickedPoint,
    selectedRegion,
  } = useAppStore()

  // Draw satellite base layer (placeholder)
  const drawBaseLayer = useCallback(
    (ctx: CanvasRenderingContext2D, width: number, height: number) => {
      // TODO: Replace with actual satellite tile rendering
      // For now, draw a gradient representing satellite imagery
      const gradient = ctx.createLinearGradient(0, 0, width, height)
      gradient.addColorStop(0, '#1a3a2e')
      gradient.addColorStop(0.5, '#2d5a3d')
      gradient.addColorStop(1, '#1a3a2e')
      ctx.fillStyle = gradient
      ctx.fillRect(0, 0, width, height)

      // Add some texture/noise to simulate satellite imagery
      ctx.fillStyle = 'rgba(0, 0, 0, 0.1)'
      for (let i = 0; i < 100; i++) {
        const x = Math.random() * width
        const y = Math.random() * height
        ctx.fillRect(x, y, 2, 2)
      }
    },
    []
  )

  // Draw overlay layers
  const drawOverlays = useCallback(
    async (
      ctx: CanvasRenderingContext2D,
      width: number,
      height: number,
      center: [number, number],
      zoom: number
    ) => {
      if (!selectedRegion) return

      // Change mask overlay
      if (mapView.activeLayers.changeMask) {
        ctx.fillStyle = 'rgba(255, 0, 0, 0.3)'
        // Draw mock change polygons
        const changeSize = 50 / zoom
        ctx.fillRect(
          width / 2 - changeSize / 2,
          height / 2 - changeSize / 2,
          changeSize,
          changeSize
        )
      }

      // Confidence overlay
      if (mapView.activeLayers.confidence) {
        const gradient = ctx.createRadialGradient(
          width / 2,
          height / 2,
          0,
          width / 2,
          height / 2,
          Math.min(width, height) / 2
        )
        gradient.addColorStop(0, 'rgba(51, 225, 255, 0.4)')
        gradient.addColorStop(1, 'rgba(51, 225, 255, 0)')
        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, width, height)
      }

      // TODO: Load actual overlay images from tile service
      // const overlayUrl = getOverlayUrl(selectedRegion, mapView.currentDate, 'changeMask')
      // const img = new Image()
      // img.src = overlayUrl
      // ctx.drawImage(img, 0, 0, width, height)
    },
    [mapView.activeLayers, mapView.currentDate, selectedRegion]
  )

  // Draw comparison mode (side-by-side or swipe)
  const drawComparison = useCallback(
    (
      ctx: CanvasRenderingContext2D,
      width: number,
      height: number,
      swipePosition: number
    ) => {
      if (!mapView.comparisonMode || !mapView.comparisonDate) return

      // Draw divider line
      ctx.strokeStyle = '#33E1FF'
      ctx.lineWidth = 2
      ctx.setLineDash([5, 5])
      ctx.beginPath()
      ctx.moveTo(swipePosition, 0)
      ctx.lineTo(swipePosition, height)
      ctx.stroke()
      ctx.setLineDash([])

      // Draw date labels
      ctx.fillStyle = '#33E1FF'
      ctx.font = '12px Inter'
      ctx.fillText(mapView.currentDate, 10, 20)
      ctx.fillText(mapView.comparisonDate, width - 100, 20)
    },
    [mapView.comparisonMode, mapView.comparisonDate, mapView.currentDate]
  )

  // Draw polygon being drawn
  const drawPolygon = useCallback(
    (ctx: CanvasRenderingContext2D, points: [number, number][]) => {
      if (points.length < 2) return

      ctx.strokeStyle = '#33E1FF'
      ctx.lineWidth = 2
      ctx.fillStyle = 'rgba(51, 225, 255, 0.1)'
      ctx.beginPath()
      ctx.moveTo(points[0][0], points[0][1])
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i][0], points[i][1])
      }
      if (points.length > 2) {
        ctx.closePath()
        ctx.fill()
      }
      ctx.stroke()

      // Draw points
      points.forEach((point) => {
        ctx.fillStyle = '#33E1FF'
        ctx.beginPath()
        ctx.arc(point[0], point[1], 4, 0, Math.PI * 2)
        ctx.fill()
      })
    },
    []
  )

  // Main render function
  const render = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height

    ctx.clearRect(0, 0, width, height)

    // Draw base layer
    drawBaseLayer(ctx, width, height)

    // Draw overlays
    drawOverlays(ctx, width, height, mapView.center, mapView.zoom)

    // Draw comparison mode
    if (mapView.comparisonMode) {
      drawComparison(ctx, width, height, width / 2)
    }

    // Draw polygon if drawing
    if (isDrawing && drawingPoints.length > 0) {
      drawPolygon(ctx, drawingPoints)
    }
  }, [
    mapView,
    isDrawing,
    drawingPoints,
    drawBaseLayer,
    drawOverlays,
    drawComparison,
    drawPolygon,
  ])

  // Handle canvas resize
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const resize = () => {
      const rect = container.getBoundingClientRect()
      canvas.width = rect.width
      canvas.height = rect.height
      render()
    }

    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [render])

  // Render on state changes
  useEffect(() => {
    render()
  }, [render])

  // Mouse handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    if (isDrawing) {
      setDrawingPoints([...drawingPoints, [x, y]])
    } else {
      setIsDragging(true)
      setDragStart([e.clientX, e.clientY])
    }
  }

  const handleMouseMove = async (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    if (isDragging && dragStart) {
      const dx = e.clientX - dragStart[0]
      const dy = e.clientY - dragStart[1]
      // TODO: Convert pixel movement to lat/lon delta
      updateMapCenter([mapView.center[0] - dx * 0.001, mapView.center[1] + dy * 0.001])
      setDragStart([e.clientX, e.clientY])
    } else if (!isDrawing && !isDragging) {
      // Show confidence on hover
      // Mock confidence calculation
      const confidence = await getConfidenceAtPoint(
        mapView.center[0] + (x - rect.width / 2) * 0.001,
        mapView.center[1] - (y - rect.height / 2) * 0.001,
        selectedRegion || 'region-1'
      )
      setTooltip({ x: e.clientX, y: e.clientY, confidence })
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
    setDragStart(null)

    if (isDrawing && drawingPoints.length > 2) {
      // Complete polygon
      setDrawnPolygon(drawingPoints)
      setIsDrawing(false)
      setDrawingPoints([])
    }
  }

  const handleClick = async (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isDrawing) return

    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    // Convert pixel to lat/lon (mock conversion)
    const lon = mapView.center[0] + (x - rect.width / 2) * 0.001
    const lat = mapView.center[1] - (y - rect.height / 2) * 0.001

    const confidence = await getConfidenceAtPoint(
      lon,
      lat,
      selectedRegion || 'region-1'
    )

    setClickedPoint({ lon, lat, confidence })
  }

  const handleZoom = (delta: number) => {
    const newZoom = Math.max(1, Math.min(20, mapView.zoom + delta))
    updateZoom(newZoom)
  }

  const handleExport = () => {
    const canvas = canvasRef.current
    if (!canvas) return

    const link = document.createElement('a')
    link.download = `terratrack-export-${Date.now()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  }

  return (
    <div ref={containerRef} className="relative w-full h-full bg-slate-dark">
      <canvas
        ref={canvasRef}
        className="w-full h-full cursor-crosshair"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleClick}
        aria-label="Interactive map viewer"
      />

      {/* Map Controls */}
      <div className="absolute top-4 right-4 flex flex-col gap-2 z-10">
        <button
          onClick={() => handleZoom(1)}
          className="p-2 bg-slate-dark/80 backdrop-blur-sm rounded-lg border border-slate-600 hover:border-accent text-slate-300 hover:text-accent transition-colors"
          aria-label="Zoom in"
        >
          <ZoomIn className="w-5 h-5" />
        </button>
        <button
          onClick={() => handleZoom(-1)}
          className="p-2 bg-slate-dark/80 backdrop-blur-sm rounded-lg border border-slate-600 hover:border-accent text-slate-300 hover:text-accent transition-colors"
          aria-label="Zoom out"
        >
          <ZoomOut className="w-5 h-5" />
        </button>
        <button
          onClick={handleExport}
          className="p-2 bg-slate-dark/80 backdrop-blur-sm rounded-lg border border-slate-600 hover:border-accent text-slate-300 hover:text-accent transition-colors"
          aria-label="Export map view"
        >
          <Download className="w-5 h-5" />
        </button>
        <button
          onClick={toggleComparisonMode}
          className={`p-2 bg-slate-dark/80 backdrop-blur-sm rounded-lg border transition-colors ${
            mapView.comparisonMode
              ? 'border-accent text-accent'
              : 'border-slate-600 hover:border-accent text-slate-300 hover:text-accent'
          }`}
          aria-label="Toggle comparison mode"
        >
          <Layers className="w-5 h-5" />
        </button>
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {tooltip && !isDragging && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute pointer-events-none z-20 glass-card rounded-lg p-2 text-sm"
            style={{ left: tooltip.x + 10, top: tooltip.y - 10 }}
          >
            <div className="text-accent font-semibold">
              Confidence: {(tooltip.confidence * 100).toFixed(1)}%
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Drawing mode indicator */}
      {isDrawing && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 glass-card rounded-lg px-4 py-2 text-sm text-accent">
          Drawing mode: Click to add points, close polygon automatically
        </div>
      )}
    </div>
  )
}

