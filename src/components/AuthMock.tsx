'use client'

import { User, Shield, Eye, Settings } from 'lucide-react'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'
import type { UserRole } from '@/types'

export default function AuthMock() {
  const { userRole, setUserRole } = useAppStore()
  const [isOpen, setIsOpen] = useState(false)

  const roles: { id: UserRole; label: string; icon: React.ComponentType<{ className?: string }>; description: string }[] = [
    {
      id: 'Admin',
      label: 'Administrator',
      icon: Shield,
      description: 'Full access to all features',
    },
    {
      id: 'Researcher',
      label: 'Researcher',
      icon: User,
      description: 'Can configure alerts and generate reports',
    },
    {
      id: 'Viewer',
      label: 'Viewer',
      icon: Eye,
      description: 'Read-only access',
    },
  ]

  const currentRole = roles.find((r) => r.id === userRole)
  const CurrentIcon = currentRole?.icon || User

  return (
    <div className="fixed bottom-4 right-4 z-30">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 glass-card rounded-lg border border-slate-600 hover:border-accent text-slate-300 hover:text-accent transition-colors"
        aria-label="Switch user role"
        aria-expanded={isOpen}
      >
        <CurrentIcon className="w-4 h-4" />
        <span className="text-sm font-medium">{userRole}</span>
        <Settings className="w-4 h-4" />
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 z-40"
              aria-hidden="true"
            />

            {/* Dropdown */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="absolute bottom-full right-0 mb-2 glass-card rounded-lg p-2 min-w-[200px] z-50"
              role="menu"
            >
              <div className="text-xs text-slate-400 px-2 py-1 mb-2">
                Switch Role (Demo)
              </div>
              {roles.map((role) => {
                const Icon = role.icon
                const isActive = role.id === userRole

                return (
                  <button
                    key={role.id}
                    onClick={() => {
                      setUserRole(role.id)
                      setIsOpen(false)
                    }}
                    className={`w-full flex items-start gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                      isActive
                        ? 'bg-accent/20 text-accent border border-accent/30'
                        : 'text-slate-300 hover:bg-slate-700'
                    }`}
                    role="menuitem"
                  >
                    <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{role.label}</div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {role.description}
                      </div>
                    </div>
                  </button>
                )
              })}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

