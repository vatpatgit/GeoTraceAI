'use client'

import {
  X, TrendingUp, TrendingDown, AlertTriangle, Map, Activity,
  BarChart3, Shield, Flame, TreePine, ChevronRight
} from 'lucide-react'
import { useMemo } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Area, AreaChart, PieChart, Pie, Cell,
} from 'recharts'
import { useAppStore } from '@/store/useAppStore'
import { getTimeSeries, getRegionSummary, getRecentAlerts, REGION_THEME, getRegionById } from '@/lib/mockData'
import { getHistoricalSummary, getHistoricalAlerts } from '@/data/historicalData'
import { format, parseISO } from 'date-fns'
import { motion } from 'framer-motion'
import AIInsightsPanel from './AIInsightsPanel'

export default function AnalyticsPanel() {
  const { analyticsPanelOpen, setAnalyticsPanelOpen, selectedRegion, mapView, selectedDate } = useAppStore()

  const timeSeries = useMemo(() => {
    const data = getTimeSeries(selectedRegion)
    return data.filter((point) => {
      const d = parseISO(point.date)
      const start = parseISO(mapView.dateRange.start)
      const end = parseISO(mapView.dateRange.end)
      return d >= start && d <= end
    })
  }, [selectedRegion, mapView.dateRange])

  const summary = useMemo(() => getRegionSummary(selectedRegion), [selectedRegion])
  const alerts = useMemo(() => getRecentAlerts(selectedRegion), [selectedRegion])
  const region = useMemo(() => getRegionById(selectedRegion), [selectedRegion])
  const theme = REGION_THEME[selectedRegion] || REGION_THEME['region-1']

  // Historical data — updates when timeline moves
  const historicalSummary = useMemo(
    () => getHistoricalSummary(selectedRegion, selectedDate),
    [selectedRegion, selectedDate]
  )
  const historicalAlerts = useMemo(
    () => getHistoricalAlerts(selectedRegion, selectedDate),
    [selectedRegion, selectedDate]
  )

  // Pie data for change breakdown
  const pieData = [
    { name: 'Deforestation', value: 45, color: '#EF4444' },
    { name: 'Wildfire', value: 25, color: '#F97316' },
    { name: 'Urban', value: 20, color: '#94A3B8' },
    { name: 'Water', value: 10, color: '#3B82F6' },
  ]

  if (!analyticsPanelOpen) return null

  return (
    <motion.div
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="h-full flex flex-col bg-[#0D1321]"
    >
      {/* Header */}
      <div className="p-4 pb-3 border-b border-white/5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-accent/20 to-cyan-500/10 flex items-center justify-center">
            <BarChart3 className="w-3.5 h-3.5 text-accent" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white tracking-wide leading-none">Analytics</h2>
            <p className="text-[9px] text-slate-500 mt-0.5">Real-time monitoring data</p>
          </div>
        </div>
        <button
          onClick={() => setAnalyticsPanelOpen(false)}
          className="p-1.5 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
          aria-label="Close analytics panel"
          id="close-analytics-btn"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Region Badge */}
      <div className="px-4 pt-3 pb-2 flex-shrink-0">
        <div className="glass-card-light rounded-lg px-3 py-2.5 flex items-center gap-2.5">
          <div className="relative">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: theme.primary }} />
            <div className="absolute inset-0 w-2 h-2 rounded-full animate-ping opacity-30" style={{ background: theme.primary }} />
          </div>
          <span className="text-xs font-medium text-slate-300 truncate flex-1">
            {region?.name || 'No region selected'}
          </span>
          <span className="text-[9px] text-slate-500 font-mono">
            {summary ? `${(summary.areaKm2 / 1000).toFixed(0)}K km²` : ''}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
        {/* Metric Cards */}
        <div className="grid grid-cols-2 gap-2.5 mt-1">
          <MetricCard
            icon={Map}
            label="Area Monitored"
            value={historicalSummary ? historicalSummary.areaMonitored : (summary ? `${(summary.areaKm2 / 1000).toFixed(0)}K km²` : '—')}
            subtext={historicalSummary ? `${historicalSummary.changePerDay} avg/day` : (summary ? `${summary.changePerDay} km²/day avg` : '')}
            color="#3B82F6"
          />
          <MetricCard
            icon={historicalSummary?.trend === 'increasing' || summary?.trend === 'increasing' ? TrendingUp : TrendingDown}
            label="Change (30d)"
            value={historicalSummary ? historicalSummary.totalChange : (summary ? `${summary.totalChange.toFixed(0)} km²` : '—')}
            subtext={historicalSummary ? `${historicalSummary.trend === 'increasing' ? '↑' : '↓'} ${historicalSummary.trend}` : (summary?.trend === 'increasing' ? '↑ Increasing' : '↓ Decreasing')}
            color={historicalSummary?.trend === 'increasing' || summary?.trend === 'increasing' ? '#EF4444' : '#10B981'}
          />
          <MetricCard
            icon={Shield}
            label="AI Confidence"
            value={historicalSummary ? historicalSummary.confidence : (summary ? `${summary.avgConfidence.toFixed(0)}%` : '—')}
            subtext="Avg detection accuracy"
            color="#33E1FF"
          />
          <MetricCard
            icon={AlertTriangle}
            label="Active Alerts"
            value={historicalSummary ? historicalSummary.activeAlerts.toString() : (summary ? summary.totalAlerts.toString() : '—')}
            subtext={historicalSummary ? `${historicalSummary.criticalAlerts} critical` : (alerts.filter((a) => a.severity === 'critical').length + ' critical')}
            color="#EF4444"
          />
        </div>

        {/* Change Area Chart */}
        <ChartCard title="Change Detection Over Time">
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={timeSeries}>
              <defs>
                <linearGradient id="changeGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={theme.primary} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={theme.primary} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => format(parseISO(d), 'dd')}
                stroke="#4B5563"
                fontSize={10}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#4B5563"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={35}
              />
              <Tooltip content={<CustomTooltip suffix=" km²" />} />
              <Area
                type="monotone"
                dataKey="change_area_km2"
                stroke={theme.primary}
                strokeWidth={2}
                fill="url(#changeGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Confidence Chart */}
        <ChartCard title="Detection Confidence">
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={timeSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => format(parseISO(d), 'dd')}
                stroke="#4B5563"
                fontSize={10}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#4B5563"
                fontSize={10}
                domain={[0.6, 1]}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                tickLine={false}
                axisLine={false}
                width={35}
              />
              <Tooltip content={<CustomTooltip suffix="%" multiplier={100} />} />
              <Line
                type="monotone"
                dataKey="avg_confidence"
                stroke="#33E1FF"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#33E1FF', strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Change Breakdown (Pie) */}
        <ChartCard title="Change Type Breakdown">
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={100} height={100}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={28}
                  outerRadius={45}
                  paddingAngle={3}
                  dataKey="value"
                  strokeWidth={0}
                >
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="flex-1 space-y-2">
              {pieData.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-sm" style={{ background: item.color }} />
                    <span className="text-xs text-slate-300">{item.name}</span>
                  </div>
                  <span className="text-xs font-semibold text-white">{item.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </ChartCard>

        {/* Alert Feed */}
        <ChartCard title="Recent Alerts">
          <div className="space-y-2">
            {alerts.slice(0, 3).map((alert) => (
              <div
                key={alert.id}
                className="flex items-start gap-2.5 p-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.05] transition-colors cursor-pointer group"
              >
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${
                  alert.severity === 'critical' ? 'bg-red-500/15' :
                  alert.severity === 'warning' ? 'bg-amber-500/15' : 'bg-blue-500/15'
                }`}>
                  {alert.type === 'wildfire' ? (
                    <Flame className={`w-3.5 h-3.5 ${
                      alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'
                    }`} />
                  ) : alert.type === 'deforestation' ? (
                    <TreePine className={`w-3.5 h-3.5 ${
                      alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'
                    }`} />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5 text-blue-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-white truncate">{alert.title}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5 line-clamp-1">
                    {alert.description}
                  </div>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-accent transition-colors flex-shrink-0 mt-1" />
              </div>
            ))}
            {alerts.length === 0 && (
              <div className="text-xs text-slate-500 text-center py-4">No recent alerts</div>
            )}
          </div>
        </ChartCard>

        {/* AI Insights */}
        <AIInsightsPanel />

        {/* Alert Count Bar Chart */}
        <ChartCard title="Daily Alert Volume">
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={timeSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => format(parseISO(d), 'dd')}
                stroke="#4B5563"
                fontSize={10}
                tickLine={false}
                axisLine={false}
              />
              <YAxis stroke="#4B5563" fontSize={10} tickLine={false} axisLine={false} width={25} />
              <Tooltip content={<CustomTooltip suffix=" alerts" />} />
              <Bar dataKey="alert_count" fill={theme.alertColor} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </motion.div>
  )
}

/* ─── Sub-components ──────────────────────────────────────────────── */

function MetricCard({
  icon: Icon,
  label,
  value,
  subtext,
  color,
}: {
  icon: React.ComponentType<{ className?: string; color?: string }>
  label: string
  value: string
  subtext: string
  color: string
}) {
  return (
    <div className="metric-card glass-card-light rounded-xl p-3">
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-6 h-6 rounded-md flex items-center justify-center"
          style={{ background: `${color}15` }}
        >
          <Icon className="w-3.5 h-3.5" color={color} />
        </div>
        <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">{label}</span>
      </div>
      <div className="text-lg font-bold text-white leading-none">{value}</div>
      {subtext && (
        <div className="text-[10px] mt-1.5" style={{ color: `${color}cc` }}>{subtext}</div>
      )}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="chart-card glass-card-light rounded-xl p-3">
      <h3 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
        {title}
      </h3>
      {children}
    </div>
  )
}

function CustomTooltip({
  active,
  payload,
  label,
  suffix = '',
  multiplier = 1,
}: any) {
  if (!active || !payload?.length) return null

  return (
    <div className="glass-card rounded-lg px-3 py-2 text-xs shadow-xl border border-white/10">
      <div className="text-slate-400 mb-1">
        {label ? format(parseISO(label), 'MMM dd, yyyy') : ''}
      </div>
      {payload.map((entry: any, i: number) => (
        <div key={i} className="font-semibold" style={{ color: entry.color || '#33E1FF' }}>
          {(entry.value * multiplier).toFixed(1)}{suffix}
        </div>
      ))}
    </div>
  )
}
