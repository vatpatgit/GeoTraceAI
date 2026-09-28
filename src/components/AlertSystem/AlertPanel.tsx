'use client'

import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, AlertTriangle, Bell, ChevronDown, Info, Loader2, RefreshCw, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertsApiError, BackendAlert, dismissAlert, listAlerts } from '@/lib/alertsApi'

const severityConfig = {
    critical: { color: '#DC2626', icon: AlertCircle, bgColor: 'bg-red-500/10' },
    warning: { color: '#FF7F00', icon: AlertTriangle, bgColor: 'bg-orange-500/10' },
    info: { color: '#0EA5E9', icon: Info, bgColor: 'bg-blue-500/10' },
}

function errorMessage(error: unknown): string {
    if (error instanceof AlertsApiError) {
        if (error.status === 401) return 'Your session has expired. Please sign in again.'
        if (error.status === 403) return 'You do not have permission to view alerts.'
        if (error.status >= 500 || error.status === 0) return 'Unable to load alerts. Please try again.'
        return error.message
    }
    return 'Unable to load alerts. Please try again.'
}

export default function AlertPanel() {
    const [expanded, setExpanded] = useState(true)
    const [alerts, setAlerts] = useState<BackendAlert[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    const loadAlerts = useCallback(async () => {
        setLoading(true)
        setError('')
        try {
            const response = await listAlerts()
            setAlerts(response.alerts)
        } catch (requestError) {
            setError(errorMessage(requestError))
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => { loadAlerts() }, [loadAlerts])

    const handleDismiss = async (alert: BackendAlert) => {
        try {
            await dismissAlert(alert.id)
            setAlerts((current) => current.filter((item) => item.id !== alert.id))
        } catch (requestError) {
            setError(errorMessage(requestError))
        }
    }

    if (!expanded) return <button onClick={() => setExpanded(true)} className="absolute bottom-4 left-4 z-20 flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-dark px-4 py-2" aria-label="Show alerts"><Bell className="h-4 w-4 text-accent" />Alerts{alerts.length > 0 && <span className="rounded bg-red-500/20 px-2 py-0.5 text-xs text-red-400">{alerts.length}</span>}</button>

    return <AnimatePresence><motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="absolute bottom-4 left-4 z-20 flex max-h-[500px] w-96 flex-col overflow-hidden rounded-lg border border-slate-600 bg-slate-dark shadow-xl"><div className="flex items-center justify-between border-b border-slate-600 bg-slate-700/50 px-4 py-3"><div className="flex items-center gap-2"><h3 className="text-sm font-semibold text-slate-300">Active Alerts</h3>{alerts.length > 0 && <span className="rounded bg-red-500/20 px-2 py-0.5 text-xs font-bold text-red-400">{alerts.length}</span>}</div><div className="flex gap-1"><button onClick={loadAlerts} className="rounded p-1 text-slate-400 hover:text-white" aria-label="Refresh alerts"><RefreshCw className="h-4 w-4" /></button><button onClick={() => setExpanded(false)} className="rounded p-1 text-slate-400 hover:text-slate-200" aria-label="Collapse alerts"><ChevronDown className="h-4 w-4" /></button></div></div><div className="flex-1 overflow-y-auto">{loading && <div className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin text-accent" />Loading alerts...</div>}{!loading && error && <div className="space-y-3 p-6 text-center"><p className="text-sm text-red-300">{error}</p><button onClick={loadAlerts} className="text-xs font-semibold text-accent">Try again</button></div>}{!loading && !error && alerts.length === 0 && <div className="p-6 text-center"><Bell className="mx-auto h-7 w-7 text-slate-600" /><p className="mt-2 text-sm text-slate-400">No active alerts</p></div>}{!loading && !error && alerts.length > 0 && <div className="space-y-2 p-3">{alerts.map((alert) => { const config = severityConfig[alert.severity as keyof typeof severityConfig] || severityConfig.info; const Icon = config.icon; return <div key={alert.id} className={`rounded border-l-4 p-3 ${config.bgColor}`} style={{ borderColor: config.color }}><div className="flex items-start gap-3"><Icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color: config.color }} /><div className="min-w-0 flex-1"><div className="text-sm font-medium text-slate-200">{alert.severity.toUpperCase()} Alert</div><div className="text-xs text-slate-400">{alert.message}</div><div className="mt-1 text-xs text-slate-500">{new Date(alert.created_at).toLocaleString()}</div></div><button onClick={() => handleDismiss(alert)} className="rounded p-1 text-slate-400 hover:text-white" aria-label={`Dismiss alert ${alert.id}`}><X className="h-3 w-3" /></button></div></div> })}</div>}</div></motion.div></AnimatePresence>
}
