'use client'

interface ProgressProps {
    value: number
    max?: number
    label?: string
    variant?: 'default' | 'success' | 'danger' | 'warning'
    showLabel?: boolean
}

export default function Progress({
    value,
    max = 100,
    label,
    variant = 'default',
    showLabel = true,
}: ProgressProps) {
    const percentage = (value / max) * 100

    const variantClass = {
        default: 'bg-accent',
        success: 'bg-green-500',
        danger: 'bg-red-500',
        warning: 'bg-yellow-500',
    }[variant]

    return (
        <div className="w-full">
            {/* Label */}
            {showLabel && (label || percentage > 0) && (
                <div className="flex items-center justify-between mb-2">
                    {label && <span className="text-xs font-medium text-slate-300">{label}</span>}
                    <span className="text-xs text-slate-400">{Math.round(percentage)}%</span>
                </div>
            )}

            {/* Bar */}
            <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                    className={`h-full ${variantClass} transition-all duration-300 rounded-full`}
                    style={{ width: `${percentage}%` }}
                />
            </div>
        </div>
    )
}
