'use client'

import { TrendingUp, TrendingDown } from 'lucide-react'

interface MetricsCardProps {
    label: string
    value: string | number
    unit?: string
    trend?: {
        direction: 'up' | 'down'
        percentage: number
        period: string
    }
    onClick?: () => void
}

export default function MetricsCard({
    label,
    value,
    unit,
    trend,
    onClick,
}: MetricsCardProps) {
    const trendColor = trend?.direction === 'up' ? 'text-red-500' : 'text-green-500'
    const TrendIcon = trend?.direction === 'up' ? TrendingUp : TrendingDown

    return (
        <button
            onClick={onClick}
            className="p-4 rounded-lg border border-slate-600 bg-slate-700/50 hover:bg-slate-700/70 transition-colors text-left"
        >
            {/* Label */}
            <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-slate-400 uppercase">{label}</h4>
                {trend && (
                    <div className={`flex items-center gap-1 text-xs font-semibold ${trendColor}`}>
                        <TrendIcon className="w-3 h-3" />
                        <span>
                            {Math.abs(trend.percentage)}% {trend.period}
                        </span>
                    </div>
                )}
            </div>

            {/* Value */}
            <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold text-slate-100">{value}</span>
                {unit && <span className="text-sm text-slate-400">{unit}</span>}
            </div>
        </button>
    )
}
