'use client'

import {
  LayoutDashboard, Map, BarChart3, Bell, FileText, Settings,
  Globe, Shield, Zap
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAppStore } from '@/store/useAppStore'

const menuItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, active: true },
  { id: 'regions', label: 'Regions', icon: Globe },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'reports', label: 'Reports', icon: FileText },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const { authUser } = useAppStore()
  const pathname = usePathname()


  return (
    <aside
      className="w-[220px] bg-[#0A0E1A] border-r border-white/[0.04] flex flex-col"
      aria-label="Main navigation"
    >
      {/* Menu Items */}
      <nav className="flex-1 p-3 space-y-0.5 mt-1" aria-label="Navigation menu">
        {menuItems.map((item) => {
          const Icon = item.icon
          const href = `/${item.id}`
          const isActive = pathname === href || (item.id === 'dashboard' && pathname === '/')
          return (
            <Link
              key={item.id}
              href={href}
              className={`nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all relative ${isActive
                ? 'bg-accent/10 text-accent'
                : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'
                }`}
              aria-label={item.label}
              id={`sidebar-${item.id}`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="text-sm font-medium">{item.label}</span>
              {/* Alert badge */}
            </Link>
          )
        })}
        {authUser?.role === 'Admin' && (
          <div className="pt-4 mt-3 border-t border-white/[0.04]">
            <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-600">Administration</div>
            <Link
              href="/admin/users"
              className={`nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all ${pathname === '/admin/users' ? 'bg-accent/10 text-accent' : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'}`}
            >
              <Shield className="w-4 h-4" />
              <span className="text-sm font-medium">Users</span>
            </Link>
          </div>
        )}
      </nav>

      {/* Bottom section */}
      <div className="p-3 border-t border-white/[0.04] space-y-3">
        {/* System Status */}
        <div className="glass-card-light rounded-lg p-3 space-y-2.5">
          <div className="flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-accent" />
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">System Status</span>
          </div>
          <div className="space-y-1.5">
            <StatusRow label="API" status="online" />
            <StatusRow label="Satellite Feed" status="online" />
            <StatusRow label="AI Detection" status="online" />
          </div>
        </div>

        {/* Version */}
        <div className="flex items-center gap-1.5 px-1">
          <Shield className="w-3 h-3 text-slate-600" />
          <span className="text-[10px] text-slate-600">v1.0.0</span>
          <span className="text-[9px] text-slate-700 ml-auto px-1.5 py-0.5 rounded bg-white/[0.03] border border-white/[0.04]">Demo</span>
        </div>
      </div>
    </aside>
  )
}

function StatusRow({ label, status }: { label: string; status: 'online' | 'offline' | 'warning' }) {
  const colors = {
    online: 'bg-emerald-400',
    warning: 'bg-amber-400',
    offline: 'bg-red-400',
  }

  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-slate-400">{label}</span>
      <div className="flex items-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full ${colors[status]} ${status === 'online' ? 'shadow-sm shadow-emerald-400/40' : ''}`} />
        <span className={`text-[10px] capitalize ${status === 'online' ? 'text-emerald-400/70' : 'text-slate-500'}`}>{status === 'online' ? 'Online' : status}</span>
      </div>
    </div>
  )
}
