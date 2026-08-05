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

  // Only Admin and Researcher can generate reports
  if (userRole === 'Viewer') {
    return null
  }

  const handleGenerate = async () => {
    setIsProcessing(true)
    setDownloadReady(false)

    // TODO: Replace with actual API call to generate report
    // const response = await fetch('/api/v1/reports/generate', {
    //   method: 'POST',
    //   body: JSON.stringify({
    //     regionId: selectedRegion,
    //     dateRange: mapView.dateRange,
    //     format: 'pdf'
    //   })
    // })

    // Simulate processing time
    await new Promise((resolve) => setTimeout(resolve, 2000))

    setIsProcessing(false)
    setDownloadReady(true)
  }

  const handleDownload = () => {
    // TODO: Replace with actual download from API
    // const response = await fetch(`/api/v1/reports/${reportId}/download`)
    // const blob = await response.blob()
    // const url = window.URL.createObjectURL(blob)
    // const a = document.createElement('a')
    // a.href = url
    // a.download = `terratrack-report-${Date.now()}.pdf`
    // a.click()

    // Mock download
    const link = document.createElement('a')
    link.href = '#'
    link.download = `terratrack-report-${Date.now()}.pdf`
    link.click()

    setReportDownloadOpen(false)
    setDownloadReady(false)
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
                    defaultValue="pdf"
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

