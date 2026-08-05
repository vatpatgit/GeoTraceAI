'use client'

import { useState, useEffect } from 'react'
import { ChevronDown, ChevronUp, AlertCircle, AlertTriangle, Info, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface Alert {
    id: string
    severity: 'critical' | 'warning' | 'info'
    message: string
    description?: string
    timestamp: string
    dismissed: boolean
}

const mockAlerts: Alert[] = [
    {
        id: '1',
        severity: 'critical',
        message: 'Wildfire Detected',
        description: 'Amazon North - 5.2 km² affected',
        timestamp: '2024-03-10T14:32:00Z',
        dismissed: false,
    },
    {
        id: '2',
        severity: 'warning',
        message: 'Deforestation Rate Increasing',
        description: 'Amazon Central - +23% vs last month',
        timestamp: '2024-03-10T10:15:00Z',
        dismissed: false,
    },
    {
        id: '3',
        severity: 'info',
        message: 'New Data Available',
        description: 'Latest satellite imagery loaded',
        timestamp: '2024-03-09T16:45:00Z',
        dismissed: false,
    },
]

export default function AlertPanel() {
    const [isExpanded, setIsExpanded] = useState(true)
    const [alerts, setAlerts] = useState<Alert[]>(mockAlerts)

    const severityConfig = {
        critical: { color: '#DC2626', icon: AlertCircle, label: 'Critical', bgColor: 'bg-red-500/10' },
        warning: { color: '#FF7F00', icon: AlertTriangle, label: 'Warning', bgColor: 'bg-orange-500/10' },
        info: { color: '#0EA5E9', icon: Info, label: 'Info', bgColor: 'bg-blue-500/10' },
    }

    const handleDismiss = (id: string) => {
        setAlerts((prev) => prev.filter((a) => a.id !== id))
    }

    const activeCount = alerts.filter((a) => !a.dismissed).length

    return (
        <>
            {/* Expand/Collapse Button (when collapsed) */}
            <AnimatePresence>
                {!isExpanded && (
                    <motion.button
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        onClick={() => setIsExpanded(true)}
                        className="absolute bottom-4 left-4 z-20 flex items-center gap-2 px-4 py-2 bg-slate-dark border border-slate-600 rounded-lg hover:bg-slate-700 transition-colors"
                        aria-label="Show alerts"
                    >
                        <span className="text-sm font-medium text-slate-300">Alerts</span>
                        {activeCount > 0 && (
                            <span className="px-2 py-0.5 text-xs font-bold rounded bg-red-500/20 text-red-400">
                                {activeCount}
                            </span>
                        )}
                        <ChevronUp className="w-4 h-4 text-slate-400" />
                    </motion.button>
                )}
            </AnimatePresence>

            {/* Alert Panel */}
            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 20 }}
                        className="absolute bottom-4 left-4 z-20 w-96 bg-slate-dark border border-slate-600 rounded-lg shadow-xl overflow-hidden flex flex-col max-h-[500px]"
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-600 bg-slate-700/50">
                            <div className="flex items-center gap-2">
                                <h3 className="text-sm font-semibold text-slate-300">Active Alerts</h3>
                                {activeCount > 0 && (
                                    <span className="px-2 py-0.5 text-xs font-bold rounded bg-red-500/20 text-red-400">
                                        {activeCount}
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={() => setIsExpanded(false)}
                                className="p-1 hover:bg-slate-600 rounded text-slate-400 hover:text-slate-200 transition-colors"
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
                                        const timeAgo = new Date(alert.timestamp).toLocaleTimeString(undefined, {
                                            month: 'short',
                                            day: 'numeric',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                        })

                                        return (
                                            <motion.div
                                                key={alert.id}
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                exit={{ opacity: 0, x: -10 }}
                                                className={`border-l-4 p-3 rounded ${config.bgColor} hover:bg-opacity-20 transition-colors`}
                                                style={{ borderColor: config.color }}
                                            >
                                                {/* Header */}
                                                <div className="flex items-start gap-3 mb-1">
                                                    <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: config.color }} />
                                                    <div className="flex-1 min-w-0">
                                                        <div className="text-sm font-medium text-slate-200 truncate">{alert.message}</div>
                                                        {alert.description && (
                                                            <div className="text-xs text-slate-400 truncate">{alert.description}</div>
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={() => handleDismiss(alert.id)}
                                                        className="p-1 hover:bg-slate-600 rounded text-slate-400 hover:text-slate-200 flex-shrink-0"
                                                        aria-label="Dismiss alert"
                                                    >
                                                        <X className="w-3 h-3" />
                                                    </button>
                                                </div>

                                                {/* Timestamp */}
                                                <div className="text-xs text-slate-400 ml-7">{timeAgo}</div>
                                            </motion.div>
                                        )
                                    })}
                                </div>
                            )}
                        </div>

                        {/* Footer */}
                        {alerts.length > 0 && (
                            <div className="bg-slate-700/50 px-4 py-2 border-t border-slate-600 flex gap-2 text-xs">
                                <button className="flex-1 px-2 py-1 bg-accent/20 hover:bg-accent/30 rounded text-accent transition-colors font-medium">
                                    History
                                </button>
                                <button className="flex-1 px-2 py-1 bg-slate-600 hover:bg-slate-500 rounded text-slate-300 transition-colors font-medium">
                                    Settings
                                </button>
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    )
}
