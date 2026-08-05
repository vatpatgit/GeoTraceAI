'use client'

import { useMemo } from 'react'
import {
  TrendingUp, TrendingDown, AlertTriangle, Activity, Eye, Sparkles, Target,
} from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { generateInsights } from '@/lib/mockData'
import type { AIInsight, InsightSeverity } from '@/lib/mockData'
import { motion, AnimatePresence } from 'framer-motion'

const SEVERITY_CONFIG: Record<InsightSeverity, { label: string; color: string; bg: string }> = {
  high: { label: 'High Risk', color: '#EF4444', bg: 'rgba(239, 68, 68, 0.1)' },
  moderate: { label: 'Moderate', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.1)' },
  informational: { label: 'Info', color: '#3B82F6', bg: 'rgba(59, 130, 246, 0.1)' },
}

function getInsightIcon(hint: AIInsight['iconHint'], className: string) {
  switch (hint) {
    case 'trending-up':
      return <TrendingUp className={className} />
    case 'trending-down':
      return <TrendingDown className={className} />
    case 'alert-triangle':
      return <AlertTriangle className={className} />
    case 'activity':
      return <Activity className={className} />
    case 'eye':
      return <Eye className={className} />
    default:
      return <Activity className={className} />
  }
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 85) return '#10B981'
  if (confidence >= 70) return '#F59E0B'
  return '#6B7280'
}

export default function AIInsightsPanel() {
  const { selectedRegion, mapView, selectedDate } = useAppStore()

  const insights = useMemo(
    () => generateInsights(selectedRegion, mapView.dateRange),
    [selectedRegion, mapView.dateRange, selectedDate] // eslint-disable-line react-hooks/exhaustive-deps
  )

  if (!insights.length) return null

  return (
    <div className="space-y-3" id="ai-insights-panel">
      {/* Section divider */}
      <div className="h-px bg-gradient-to-r from-transparent via-purple-500/20 to-transparent" />

      {/* Section Header */}
      <div className="flex items-center gap-2.5">
        <div className="w-6 h-6 rounded-md bg-gradient-to-br from-purple-500/20 to-fuchsia-500/10 flex items-center justify-center shadow-sm shadow-purple-500/10">
          <Sparkles className="w-3 h-3 text-purple-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider leading-none">
            AI Insights
          </h3>
          <p className="text-[9px] text-slate-500 mt-0.5">Powered by pattern analysis</p>
        </div>
        <span className="text-[9px] text-purple-400/60 font-semibold px-2 py-0.5 rounded-full bg-purple-500/8 border border-purple-500/10">
          {insights.length} found
        </span>
      </div>

      {/* Insight Cards */}
      <AnimatePresence mode="wait">
        <motion.div
          key={selectedRegion}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="space-y-2.5"
        >
          {insights.map((insight, index) => (
            <InsightCard key={insight.id} insight={insight} index={index} />
          ))}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

function InsightCard({ insight, index }: { insight: AIInsight; index: number }) {
  const severity = SEVERITY_CONFIG[insight.severity]
  const confColor = getConfidenceColor(insight.confidence)

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.1 }}
      className={`insight-card severity-${insight.severity} p-3 pl-4`}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: severity.bg }}
        >
          {getInsightIcon(insight.iconHint, `w-3.5 h-3.5`)}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {/* Severity badge */}
            <span
              className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{
                color: severity.color,
                background: severity.bg,
              }}
            >
              {severity.label}
            </span>

            {/* Confidence badge */}
            <span
              className="text-[9px] font-semibold px-1.5 py-0.5 rounded"
              style={{
                color: confColor,
                background: `${confColor}15`,
              }}
            >
              {insight.confidence}%
            </span>

            {/* Percentage change badge */}
            {insight.percentChange !== 0 && (
              <span
                className="text-[10px] font-semibold ml-auto flex items-center gap-0.5"
                style={{ color: insight.percentChange > 0 ? '#EF4444' : '#10B981' }}
              >
                {insight.percentChange > 0 ? '↑' : '↓'}
                {Math.abs(insight.percentChange)}%
              </span>
            )}
          </div>

          <div className="text-xs font-medium text-white leading-snug mb-1">
            {insight.title}
          </div>

          <div className="text-[10px] text-slate-400 leading-relaxed">
            {insight.description}
          </div>

          {/* Causal reasoning */}
          {insight.reasoning && (
            <div className="mt-2 pt-2 border-t border-white/5">
              <div className="flex items-center gap-1.5 mb-1">
                <Sparkles className="w-2.5 h-2.5 text-purple-400/70" />
                <span className="text-[9px] font-semibold uppercase tracking-wider text-purple-400/70">
                  Why
                </span>
              </div>
              <div className="text-[10px] text-slate-500 leading-relaxed italic">
                {insight.reasoning}
              </div>
            </div>
          )}

          {/* Recommended Action */}
          {insight.recommendation && (
            <div className="mt-2 pt-2 border-t border-white/5">
              <div className="flex items-center gap-1.5 mb-1">
                <Target className="w-2.5 h-2.5 text-emerald-400/70" />
                <span className="text-[9px] font-semibold uppercase tracking-wider text-emerald-400/70">
                  Recommended Action
                </span>
              </div>
              <div className="text-[10px] text-emerald-300/60 leading-relaxed">
                {insight.recommendation}
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}

