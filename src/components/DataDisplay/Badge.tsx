'use client'

interface BadgeProps {
    label: string
    variant?: 'default' | 'success' | 'danger' | 'warning' | 'info'
    icon?: React.ReactNode
    onRemove?: () => void
}

export default function Badge({ label, variant = 'default', icon, onRemove }: BadgeProps) {
    const variantClass = {
        default: 'bg-slate-700 text-slate-100',
        success: 'bg-green-900/40 text-green-300 border border-green-700/40',
        danger: 'bg-red-900/40 text-red-300 border border-red-700/40',
        warning: 'bg-yellow-900/40 text-yellow-300 border border-yellow-700/40',
        info: 'bg-blue-900/40 text-blue-300 border border-blue-700/40',
    }[variant]

    return (
        <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${variantClass}`}>
            {icon}
            <span>{label}</span>
            {onRemove && (
                <button
                    onClick={onRemove}
                    className="ml-1 hover:opacity-70 transition-opacity"
                >
                    ×
                </button>
            )}
        </div>
    )
}
