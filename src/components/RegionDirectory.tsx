'use client'

import { useEffect, useState } from 'react'
import { AlertCircle, Loader2, MapPin, RefreshCw } from 'lucide-react'
import { fetchRegions } from '@/lib/mockApi'
import type { Region } from '@/types'

export default function RegionDirectory() {
    const [regions, setRegions] = useState<Region[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    const loadRegions = async () => {
        setLoading(true)
        setError('')
        try {
            setRegions(await fetchRegions())
        } catch {
            setError('Unable to load regions. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { loadRegions() }, [])

    return <section className="mx-auto max-w-5xl px-6 py-10"><div className="flex items-end justify-between gap-4"><div><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent"><MapPin className="h-4 w-4" /> Monitoring</div><h1 className="mt-3 text-3xl font-semibold text-white">Regions</h1><p className="mt-2 text-sm text-slate-400">Regions are loaded from the TerraTrack backend.</p></div><button onClick={loadRegions} className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 hover:border-accent/50 hover:text-accent"><RefreshCw className="h-4 w-4" /> Refresh</button></div>{loading && <div className="mt-8 flex items-center gap-3 rounded-xl border border-white/10 p-8 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin text-accent" />Loading regions...</div>}{error && <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/10 p-5 text-sm text-red-200"><AlertCircle className="mb-2 h-5 w-5" />{error}</div>}{!loading && !error && regions.length === 0 && <div className="mt-8 rounded-xl border border-white/10 p-10 text-center text-sm text-slate-400">No monitoring regions are available.</div>}{!loading && !error && regions.length > 0 && <div className="mt-8 grid gap-4 sm:grid-cols-2">{regions.map((region) => <article key={region.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-5"><h2 className="font-semibold text-white">{region.name}</h2><p className="mt-2 text-sm text-slate-400">{region.description || 'No description available.'}</p><div className="mt-4 flex items-center justify-between text-xs text-slate-500"><span>{region.areaKm2.toLocaleString()} km²</span><span>{region.riskLevel || 'Unrated'} risk</span></div></article>)}</div>}</section>
}
