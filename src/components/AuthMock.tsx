'use client'

import { User, Settings, LogOut, LogIn } from 'lucide-react'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'
import { loginWithCredentials, logoutUser } from '@/lib/mockApi'

export default function AuthMock() {
  const { userRole, setUserRole, authUser, setAuthUser, setAuthStatus } = useAppStore()
  const [isOpen, setIsOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const CurrentIcon = User

  const handleLogin = async () => {
    setIsSubmitting(true)
    setError('')

    const result = await loginWithCredentials(email, password)
    if (!result?.user) {
      setError('Authentication failed. Check your email and password.')
      setIsSubmitting(false)
      return
    }

    setAuthUser(result.user)
    setUserRole(result.user.role)
    setAuthStatus('authenticated')
    setIsOpen(false)
    setIsSubmitting(false)
  }

  const handleLogout = () => {
    logoutUser()
    setAuthUser(null)
    setUserRole('Viewer')
    setAuthStatus('unauthenticated')
    setIsOpen(false)
  }

  return (
    <div className="fixed bottom-4 right-4 z-30">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 glass-card rounded-lg border border-slate-600 hover:border-accent text-slate-300 hover:text-accent transition-colors"
        aria-label="User account"
        aria-expanded={isOpen}
      >
        <CurrentIcon className="w-4 h-4" />
        <span className="text-sm font-medium">{authUser?.role ?? userRole}</span>
        <Settings className="w-4 h-4" />
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 z-40"
              aria-hidden="true"
            />

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="absolute bottom-full right-0 mb-2 glass-card rounded-lg p-3 min-w-[260px] z-50"
              role="menu"
            >
              {authUser ? (
                <div className="space-y-3">
                  <div className="text-xs text-slate-400">Authenticated Session</div>
                  <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
                    <div className="text-sm font-medium text-white">{authUser.name}</div>
                    <div className="text-xs text-slate-400">{authUser.email}</div>
                    <div className="mt-2 inline-flex rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-accent">{authUser.role}</div>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-2 text-sm text-slate-200 hover:border-red-500/40 hover:text-red-300"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="text-xs text-slate-400">Backend Authentication</div>
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Email"
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                  />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                  />
                  {error && <div className="text-xs text-red-400">{error}</div>}
                  <button
                    onClick={handleLogin}
                    disabled={isSubmitting}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-50"
                  >
                    <LogIn className="w-4 h-4" />
                    {isSubmitting ? 'Signing in...' : 'Sign in'}
                  </button>
                </div>
              )}

            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

