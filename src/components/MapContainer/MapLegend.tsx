'use client'

import { useState } from 'react'
import { X } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'

export default function MapLegend() {
    const [isVisible, setIsVisible] = useState(true)
    const { mapView, toggleLayer } = useAppStore()

    if (!isVisible) {
        return (
            <button
                onClick={() => setIsVisible(true)}
                className="absolute top-4 right-4 z-10 px-3 py-2 bg-slate-dark border border-slate-600 rounded hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
                aria-label="Show legend"
            >
                Legend
            </button>
        )
    }

    const legendItems = [
        {
            id: 'satellite',
            label: 'Satellite Imagery',
            active: mapView.activeLayers.satellite,
            description: 'Base map tiles from Sentinel-2',
        },
        {
            id: 'changeMask',
            label: 'Change Detection',
            active: mapView.activeLayers.changeMask,
            description: 'Areas with detected changes',
            breakdown: [
                { label: 'Deforestation', color: '#DC2626', percent: 45 },
                { label: 'Wildfire', color: '#FF7F00', percent: 25 },
                { label: 'Urban Expansion', color: '#808080', percent: 20 },
                { label: 'Water Changes', color: '#0066CC', percent: 10 },
            ],
        },
        {
            id: 'confidence',
            label: 'Confidence Heatmap',
            active: mapView.activeLayers.confidence,
            description: 'Detection confidence level (0-100%)',
        },
    ]

    return (
        <div className="absolute top-4 right-4 z-10 bg-slate-dark border border-slate-600 rounded-lg p-4 max-w-xs shadow-lg">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-300">Legend</h3>
                <button
                    onClick={() => setIsVisible(false)}
                    className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-slate-200 transition-colors"
                    aria-label="Hide legend"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>

            {/* Legend Items */}
            <div className="space-y-3 text-sm">
                {legendItems.map((item) => (
                    <div key={item.id}>
                        <label className="flex items-center gap-2 cursor-pointer mb-1">
                            <input
                                type="checkbox"
                                checked={item.active}
                                onChange={() => toggleLayer(item.id as 'satellite' | 'changeMask' | 'confidence')}
                                className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-accent focus:ring-2 focus:ring-accent"
                            />
                            <span className="text-slate-300 font-medium">{item.label}</span>
                        </label>
                        <p className="text-xs text-slate-400 ml-6 mb-2">{item.description}</p>

                        {/* Breakdown colors */}
                        {item.breakdown && (
                            <div className="ml-6 space-y-1">
                                {item.breakdown.map((color) => (
                                    <div key={color.label} className="flex items-center gap-2">
                                        <div
                                            className="w-3 h-3 rounded"
                                            style={{ backgroundColor: color.color }}
                                        />
                                        <span className="text-xs text-slate-400">
                                            {color.label} ({color.percent}%)
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Gradient for confidence */}
                        {item.id === 'confidence' && item.active && (
                            <div className="ml-6">
                                <div className="h-2 rounded bg-gradient-to-r from-red-500 via-yellow-500 to-green-500 mb-1" />
                                <div className="flex justify-between text-xs text-slate-400">
                                    <span>Low</span>
                                    <span>High</span>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            <hr className="my-3 border-slate-600" />

            {/* Footer */}
            <div className="text-xs text-slate-400 space-y-0.5">
                <p>Data source: Sentinel-2</p>
                <p>Updated: Today 2h ago</p>
            </div>
        </div>
    )
}
