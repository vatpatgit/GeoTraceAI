'use client'

import { X, Send, CheckCircle } from 'lucide-react'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'

export default function AlertConfigurator() {
  const { alertConfigOpen, setAlertConfigOpen, alertConfig, setAlertConfig, userRole, selectedRegion } =
    useAppStore()
  const [testSuccess, setTestSuccess] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  if (userRole === 'Viewer') {
    return null
  }

  const handleTest = async () => {
    const token = localStorage.getItem('terratrack_access_token')
    if (!token) return

    const body = {
      region_id: selectedRegion,
      change_type: 'deforestation',
      threshold: alertConfig.sensitivity / 100,
    }

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1'}/alerts/config`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      setError('Alert test failed. Check your permissions and configuration.')
      return
    }
    setError('')
    setTestSuccess(true)
    setTimeout(() => setTestSuccess(false), 3000)
  }

  const handleSave = async () => {
    const token = localStorage.getItem('terratrack_access_token')
    if (!token) return

    setIsSaving(true)

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1'}/alerts/config`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        region_id: selectedRegion,
        change_type: 'deforestation',
        threshold: alertConfig.sensitivity / 100,
      }),
    })

    if (!response.ok) {
      setError('Alert configuration could not be saved.')
      setIsSaving(false)
      return
    }
    setError('')
    setIsSaving(false)
    setAlertConfigOpen(false)
  }

  return (
    <AnimatePresence>
      {alertConfigOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setAlertConfigOpen(false)}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            aria-hidden="true"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            role="dialog"
            aria-labelledby="alert-config-title"
            aria-modal="true"
          >
            <div className="glass-card rounded-lg p-6 max-w-md w-full max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <h2
                  id="alert-config-title"
                  className="text-xl font-semibold text-slate-200"
                >
                  Alert Configuration
                </h2>
                <button
                  onClick={() => setAlertConfigOpen(false)}
                  className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-accent transition-colors"
                  aria-label="Close alert configuration"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Content */}
              <div className="space-y-6">
                {/* Sensitivity Slider */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Sensitivity: {alertConfig.sensitivity}%
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={alertConfig.sensitivity}
                    onChange={(e) =>
                      setAlertConfig({ sensitivity: parseInt(e.target.value) })
                    }
                    className="w-full h-2 bg-slate rounded-lg appearance-none cursor-pointer accent-accent"
                    aria-label="Alert sensitivity"
                  />
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>Low</span>
                    <span>High</span>
                  </div>
                </div>

                {/* Email Input */}
                <div>
                  <label
                    htmlFor="alert-email"
                    className="block text-sm font-medium text-slate-300 mb-2"
                  >
                    Email Notifications
                  </label>
                  <input
                    id="alert-email"
                    type="email"
                    value={alertConfig.email}
                    onChange={(e) => setAlertConfig({ email: e.target.value })}
                    placeholder="alerts@example.com"
                    className="w-full px-3 py-2 bg-slate rounded-lg border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                    aria-label="Email for alerts"
                  />
                  <p className="text-xs text-slate-400 mt-1">
                    TODO: Replace with actual email validation and API integration
                  </p>
                </div>

                {/* Webhook Input */}
                <div>
                  <label
                    htmlFor="alert-webhook"
                    className="block text-sm font-medium text-slate-300 mb-2"
                  >
                    Webhook URL
                  </label>
                  <input
                    id="alert-webhook"
                    type="url"
                    value={alertConfig.webhookUrl}
                    onChange={(e) =>
                      setAlertConfig({ webhookUrl: e.target.value })
                    }
                    placeholder="https://api.example.com/webhook"
                    className="w-full px-3 py-2 bg-slate rounded-lg border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                    aria-label="Webhook URL for alerts"
                  />
                  <p className="text-xs text-slate-400 mt-1">
                    TODO: Replace with actual webhook validation and API integration
                  </p>
                </div>

                {/* Test Button */}
                {error && <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg">{error}</div>}
                <button
                  onClick={handleTest}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-accent/20 hover:bg-accent/30 border border-accent/30 rounded-lg text-accent transition-colors"
                >
                  <Send className="w-4 h-4" />
                  <span>Test Configuration</span>
                </button>

                {/* Success Toast */}
                <AnimatePresence>
                  {testSuccess && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="flex items-center gap-2 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-400"
                    >
                      <CheckCircle className="w-5 h-5" />
                      <span className="text-sm">Test alert sent successfully!</span>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Action Buttons */}
                <div className="flex gap-3 pt-4 border-t border-slate-700">
                  <button
                    onClick={() => setAlertConfigOpen(false)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className="flex-1 px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-background font-medium transition-colors disabled:opacity-50"
                  >
                    {isSaving ? 'Saving...' : 'Save Configuration'}
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

