'use client'

import { Search, Bell, User, BarChart3, Satellite, AlertTriangle } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { REGIONS } from '@/lib/mockData'
import { BackendAlert, listAlerts } from '@/lib/alertsApi'

export default function Header() {
  const { setAnalyticsPanelOpen, analyticsPanelOpen, regions } = useAppStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [showSearchResults, setShowSearchResults] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const notifRef = useRef<HTMLDivElement>(null)
  const { setSelectedRegion } = useAppStore()

  const [alerts, setAlerts] = useState<BackendAlert[]>([])

  useEffect(() => {
    listAlerts().then((response) => setAlerts(response.alerts)).catch(() => setAlerts([]))
  }, [])

  // Filter regions by search
  const searchResults = searchQuery.length > 0
    ? (regions.length > 0 ? regions : REGIONS).filter((r) =>
      r.name.toLowerCase().includes(searchQuery.toLowerCase())
    )
    : []

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSearchResults(false)
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <header className="h-14 bg-[#0D1321] border-b border-white/5 flex items-center justify-between px-5 flex-shrink-0">
      {/* Left: Logo + Search */}
      <div className="flex items-center gap-4 flex-1">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-cyan-400 flex items-center justify-center shadow-lg shadow-accent/20">
            <Satellite className="w-4 h-4 text-[#0A0F1C]" />
          </div>
          <div className="hidden sm:block">
            <div className="text-sm font-bold text-white tracking-tight leading-none">TerraTrack</div>
            <div className="text-[9px] text-slate-400 uppercase tracking-[0.15em] mt-0.5">AI Monitoring</div>
          </div>
        </div>

        {/* Separator */}
        <div className="hidden sm:block w-px h-6 bg-white/[0.06] ml-1" />

        {/* Search */}
        <div ref={searchRef} className="relative flex-1 max-w-md ml-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search regions..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setShowSearchResults(true)
            }}
            onFocus={() => searchQuery.length > 0 && setShowSearchResults(true)}
            className="w-full pl-9 pr-4 py-2 bg-white/[0.04] rounded-lg border border-white/5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent/30 focus:bg-white/[0.06] transition-all"
            aria-label="Search regions"
            id="search-input"
          />
          {/* Search Results Dropdown */}
          {showSearchResults && searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 glass-card rounded-lg shadow-2xl overflow-hidden z-50">
              {searchResults.map((region) => (
                <button
                  key={region.id}
                  onClick={() => {
                    setSelectedRegion(region.id)
                    setSearchQuery('')
                    setShowSearchResults(false)
                  }}
                  className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-white/5 hover:text-accent transition-colors flex items-center gap-2"
                >
                  <div className="w-1.5 h-1.5 rounded-full bg-accent/50" />
                  {region.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1.5">
        {/* Status indicator */}
        <div className="hidden md:flex items-center gap-2 mr-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/15">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
          <span className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider">Live</span>
        </div>

        {/* Divider */}
        <div className="hidden md:block w-px h-5 bg-white/[0.06] mx-1" />

        {/* Analytics Toggle */}
        <button
          onClick={() => setAnalyticsPanelOpen(!analyticsPanelOpen)}
          className={`p-2 rounded-lg transition-all ${analyticsPanelOpen
            ? 'bg-accent/10 text-accent'
            : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          aria-label="Toggle analytics panel"
          id="toggle-analytics-btn"
          title="Toggle Analytics"
        >
          <BarChart3 className="w-4 h-4" />
        </button>

        {/* Notifications */}
        <div ref={notifRef} className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg text-slate-400 hover:bg-white/5 hover:text-white transition-all"
            aria-label="Notifications"
            id="notifications-btn"
          >
            <Bell className="w-4 h-4" />
            {alerts.length > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full ring-2 ring-[#0D1321]" />
            )}
          </button>

          {/* Notification Dropdown */}
          {showNotifications && (
            <div className="absolute top-full right-0 mt-2 w-80 glass-card rounded-xl shadow-2xl z-50 overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5">
                <div className="text-xs font-semibold text-white">Notifications</div>
              </div>
              <div className="max-h-64 overflow-y-auto">
                {alerts.length === 0 && (
                  <div className="px-4 py-6 text-xs text-slate-500 text-center">No notifications</div>
                )}
                {alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="px-4 py-3 hover:bg-white/[0.03] transition-colors border-b border-white/[0.03] last:border-b-0 cursor-pointer"
                  >
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${alert.severity === 'critical' ? 'text-red-400' :
                        alert.severity === 'warning' ? 'text-amber-400' : 'text-blue-400'
                        }`} />
                      <div>
                        <div className="text-xs font-medium text-white">{alert.severity.toUpperCase()} Alert</div>
                        <div className="text-[10px] text-slate-400 mt-0.5 line-clamp-1">{alert.message}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* User */}
        <button
          className="flex items-center gap-2 p-1 pl-1.5 rounded-lg hover:bg-white/5 transition-all ml-1 group"
          aria-label="User menu"
          id="user-menu-btn"
        >
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent/30 to-purple-500/30 flex items-center justify-center border border-white/10 group-hover:border-accent/30 transition-colors ring-2 ring-transparent group-hover:ring-accent/10">
            <User className="w-3.5 h-3.5 text-accent" />
          </div>
        </button>
      </div>
    </header>
  )
}
