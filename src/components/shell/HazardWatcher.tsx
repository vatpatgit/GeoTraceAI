'use client'

import { useEffect, useRef } from 'react'
import { api } from '@/lib/api'
import { HAZARD_RANK } from '@/lib/api/hazards'
import { useAppStore } from '@/store/useAppStore'

const POLL_MS = 120_000 // the server shares one upstream fetch per minute across all users, so this stays polite

/** Keeps the hazard inbox current while the app is open and announces NEW unread alerts once (a single toast per poll, never a flood). */
export default function HazardWatcher() {
  const seen = useRef<Set<string>>(new Set())
  const toast = useAppStore((s) => s.toast)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        await api.hazards.refresh({})
        const unread = await api.hazards.list({ unread: true, limit: 50 })
        if (!alive) return
        const fresh = unread.filter((a) => !seen.current.has(a.id))
        fresh.forEach((a) => seen.current.add(a.id))
        if (fresh.length) {
          const top = [...fresh].sort((a, b) => HAZARD_RANK[b.severity] - HAZARD_RANK[a.severity])[0]
          const more = fresh.length > 1 ? ` (+${fresh.length - 1} more)` : ''
          toast(HAZARD_RANK[top.severity] >= 2 ? 'error' : 'info', `Hazard alert near ${top.aoi_name ?? 'your area'}: ${top.title}${more}. See Alerts.`)
        }
      } catch { /* feed or network unavailable: the Alerts page shows the real error on demand */ }
    }
    void tick()
    const t = setInterval(() => void tick(), POLL_MS)
    return () => { alive = false; clearInterval(t) }
  }, [toast])

  return null
}
