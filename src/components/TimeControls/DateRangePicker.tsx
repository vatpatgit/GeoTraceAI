'use client'

import { useState } from 'react'
import { Calendar } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { parseISO, format, addDays, subDays } from 'date-fns'

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
        const startDate = subDays(endDate, days)

        setDateRange({
            start: format(startDate, 'yyyy-MM-dd'),
            end: format(endDate, 'yyyy-MM-dd'),
        })
        setIsOpen(false)
    }

    const handleStartChange = (value: string) => {
        setDateRange({ ...mapView.dateRange, start: value })
    }

    const handleEndChange = (value: string) => {
        setDateRange({ ...mapView.dateRange, end: value })
    }

    const startDate = mapView.dateRange.start
    const endDate = mapView.dateRange.end

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-2 px-3 py-2 bg-slate rounded-lg border border-slate-600 hover:border-accent text-left transition-colors whitespace-nowrap"
                aria-expanded={isOpen}
            >
                <Calendar className="w-4 h-4 text-accent flex-shrink-0" />
                <span className="text-sm text-slate-300 hidden sm:inline">
                    {startDate} to {endDate}
                </span>
                <span className="text-sm text-slate-300 sm:hidden">{startDate}</span>
            </button>

            {isOpen && (
                <div className="absolute top-full left-0 mt-2 bg-slate-dark border border-slate-600 rounded-lg p-4 shadow-lg z-30 w-80">
                    {/* Quick Preset Ranges */}
                    <div className="mb-4">
                        <h4 className="text-xs font-semibold text-slate-400 mb-2 uppercase">Quick Select</h4>
                        <div className="grid grid-cols-2 gap-2">
                            {presetRanges.map((preset) => (
                                <button
                                    key={preset.days}
                                    onClick={() => handlePresetSelect(preset.days)}
                                    className="text-xs px-3 py-2 bg-slate-700 hover:bg-slate-600 hover:text-accent rounded text-slate-300 transition-colors font-medium"
                                >
                                    {preset.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <hr className="border-slate-600 mb-4" />

                    {/* Custom Date Inputs */}
                    <div className="space-y-3">
                        <div>
                            <label className="text-xs font-medium text-slate-400 block mb-1 uppercase">Start Date</label>
                            <input
                                type="date"
                                value={startDate}
                                onChange={(e) => handleStartChange(e.target.value)}
                                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                            />
                        </div>

                        <div>
                            <label className="text-xs font-medium text-slate-400 block mb-1 uppercase">End Date</label>
                            <input
                                type="date"
                                value={endDate}
                                onChange={(e) => handleEndChange(e.target.value)}
                                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
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
