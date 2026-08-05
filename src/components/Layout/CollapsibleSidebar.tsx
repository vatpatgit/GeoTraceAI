'use client'

import { useState } from 'react'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import Sidebar from '../Sidebar'

export default function CollapsibleSidebar() {
  const [isCollapsed, setIsCollapsed] = useState(false)

  return (
    <div className="relative flex flex-shrink-0">
      {/* Sidebar */}
      <div
        className={`transition-all duration-300 ease-in-out overflow-hidden ${
          isCollapsed ? 'w-0' : 'w-[220px]'
        }`}
      >
        <Sidebar />
      </div>

      {/* Toggle Button */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute top-3 -right-4 z-30 p-1 bg-[#0D1321] border border-white/[0.06] rounded-md hover:bg-white/5 transition-all group"
        aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        id="toggle-sidebar-btn"
      >
        {isCollapsed ? (
          <PanelLeftOpen className="w-3.5 h-3.5 text-slate-500 group-hover:text-accent transition-colors" />
        ) : (
          <PanelLeftClose className="w-3.5 h-3.5 text-slate-500 group-hover:text-accent transition-colors" />
        )}
      </button>
    </div>
  )
}
