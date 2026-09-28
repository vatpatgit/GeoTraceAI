'use client'

import { X, Download, Loader2, FileText } from 'lucide-react'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'

export default function ReportDownloader() {
  const { reportDownloadOpen, setReportDownloadOpen, mapView, selectedRegion, userRole } =
    useAppStore()
  const [isProcessing, setIsProcessing] = useState(false)
  const [downloadReady, setDownloadReady] = useState(false)
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
  const [format, setFormat] = useState<'pdf' | 'csv' | 'json'>('pdf')
  const [error, setError] = useState('')

  if (userRole === 'Viewer') {
    return null
  }

  const handleGenerate = async () => {
    setIsProcessing(true)
    setDownloadReady(false)
    setError('')

    const token = localStorage.getItem('terratrack_access_token')
    const regionId = selectedRegion
    if (!regionId) {
      setError('Select a region before generating a report.')
      setIsProcessing(false)
      return
    }

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1'}/changes/summary?region_id=${regionId}&date_from=${encodeURIComponent(mapView.dateRange.start)}&date_to=${encodeURIComponent(mapView.dateRange.end)}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      )

      if (!response.ok) {
        throw new Error('Report generation failed')
      }

      const payload = await response.json()
      const rows = Object.entries(payload.by_type || {}).map(([type, count]) => `${type},${count}`)
      const csv = ['change_type,count', ...rows].join('\n')
      const pdf = `%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 56 >>\nstream\nBT /F1 12 Tf 72 720 Td (TerraTrack report) Tj ET\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF`
      const content = format === 'csv' ? csv : format === 'pdf' ? pdf : JSON.stringify(payload, null, 2)
      const mime = format === 'csv' ? 'text/csv' : format === 'pdf' ? 'application/pdf' : 'application/json'
      const blob = new Blob([content], { type: mime })
      const url = URL.createObjectURL(blob)
      setDownloadUrl(url)
      setDownloadReady(true)
    } catch {
      setError('Report generation failed. Please try again.')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleDownload = () => {
    if (!downloadUrl) return

    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = `terratrack-report-${Date.now()}.${format}`
    link.click()

    setReportDownloadOpen(false)
    setDownloadReady(false)
    setDownloadUrl(null)
  }

  return (
    <AnimatePresence>
      {reportDownloadOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setReportDownloadOpen(false)}
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
            aria-labelledby="report-download-title"
            aria-modal="true"
          >
            <div className="glass-card rounded-lg p-6 max-w-md w-full">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <h2
                  id="report-download-title"
                  className="text-xl font-semibold text-slate-200"
                >
                  Generate Report
                </h2>
                <button
                  onClick={() => setReportDownloadOpen(false)}
                  className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-accent transition-colors"
                  aria-label="Close report download"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Content */}
              <div className="space-y-6">
                {/* Report Info */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm text-slate-300">
                    <FileText className="w-4 h-4" />
                    <span>Region: {selectedRegion || 'All'}</span>
                  </div>
                  <div className="text-sm text-slate-400 pl-6">
                    Date Range: {mapView.dateRange.start} to {mapView.dateRange.end}
                  </div>
                </div>

                {/* Format Selection */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Format
                  </label>
                  <select
                    className="w-full px-3 py-2 bg-slate rounded-lg border border-slate-600 text-white focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                    value={format}
                    onChange={(event) => setFormat(event.target.value as 'pdf' | 'csv' | 'json')}
                    aria-label="Report format"
                  >
                    <option value="pdf">PDF</option>
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                  </select>
                </div>

                {/* Status */}
                {isProcessing && (
                  <div className="flex items-center gap-3 p-4 bg-slate-700/50 rounded-lg">
                    <Loader2 className="w-5 h-5 text-accent animate-spin" />
                    <span className="text-sm text-slate-300">
                      Processing report...
                    </span>
                  </div>
                )}

                {downloadReady && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-center gap-3 p-4 bg-green-500/20 border border-green-500/30 rounded-lg"
                  >
                    <Download className="w-5 h-5 text-green-400" />
                    <span className="text-sm text-green-400">
                      Report ready for download
                    </span>
                  </motion.div>
                )}

                {error && <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg">{error}</div>}

                {/* Action Buttons */}
                <div className="flex gap-3 pt-4 border-t border-slate-700">
                  <button
                    onClick={() => {
                      setReportDownloadOpen(false)
                      setDownloadReady(false)
                    }}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
                  >
                    Cancel
                  </button>
                  {downloadReady ? (
                    <button
                      onClick={handleDownload}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-background font-medium transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      Download
                    </button>
                  ) : (
                    <button
                      onClick={handleGenerate}
                      disabled={isProcessing}
                      className="flex-1 px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-background font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isProcessing ? 'Processing...' : 'Generate Report'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

