'use client'

import { ZoomIn, ZoomOut, Maximize2, Home } from 'lucide-react'
import { MAP_GL_CSS_PREFIX } from '@/services/maps/mapProvider'

export default function MapControls() {
    const handleZoomIn = () => {
        // GL library will auto-handle zoom via NavigationControl
    }

    const handleZoomOut = () => {
        // GL library will auto-handle zoom via NavigationControl
    }

    const handleFullscreen = () => {
        const container = document.querySelector(`[class*="${MAP_GL_CSS_PREFIX}"]`)
        if (container && (container as any).requestFullscreen) {
            ; (container as any).requestFullscreen()
        }
    }

    const handleReset = () => {
        // Reset to default center/zoom
        // This would be handled through Mapbox API
    }

    return (
        <div className="absolute top-4 right-4 z-10 flex flex-col gap-2">
            {/* Zoom Controls */}
            <div className="bg-white rounded-lg shadow-lg overflow-hidden">
                <button
                    onClick={handleZoomIn}
                    className="w-10 h-10 flex items-center justify-center hover:bg-gray-100 transition-colors border-b border-gray-200"
                    title="Zoom in"
                    aria-label="Zoom in"
                >
                    <ZoomIn className="w-5 h-5 text-gray-700" />
                </button>
                <button
                    onClick={handleZoomOut}
                    className="w-10 h-10 flex items-center justify-center hover:bg-gray-100 transition-colors"
                    title="Zoom out"
                    aria-label="Zoom out"
                >
                    <ZoomOut className="w-5 h-5 text-gray-700" />
                </button>
            </div>

            {/* Other Controls */}
            <div className="bg-white rounded-lg shadow-lg overflow-hidden">
                <button
                    onClick={handleReset}
                    className="w-10 h-10 flex items-center justify-center hover:bg-gray-100 transition-colors border-b border-gray-200"
                    title="Reset view"
                    aria-label="Reset view"
                >
                    <Home className="w-5 h-5 text-gray-700" />
                </button>
                <button
                    onClick={handleFullscreen}
                    className="w-10 h-10 flex items-center justify-center hover:bg-gray-100 transition-colors"
                    title="Fullscreen"
                    aria-label="Fullscreen"
                >
                    <Maximize2 className="w-5 h-5 text-gray-700" />
                </button>
            </div>
        </div>
    )
}
