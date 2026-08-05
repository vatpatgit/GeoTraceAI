'use client'

import { AlertCircle } from 'lucide-react'

interface EmptyStateProps {
    icon?: React.ComponentType<{ className?: string }>
    title: string
    description?: string
    action?: {
        label: string
        onClick: () => void
    }
}

export default function EmptyState({
    icon: Icon = AlertCircle,
    title,
    description,
    action,
}: EmptyStateProps) {
    return (
        <div className="flex flex-col items-center justify-center h-full p-8 text-center">
            <Icon className="w-12 h-12 text-slate-500 mb-4" />
            <h3 className="text-lg font-semibold text-slate-300 mb-2">{title}</h3>
            {description && <p className="text-sm text-slate-400 mb-4 max-w-sm">{description}</p>}
            {action && (
                <button
                    onClick={action.onClick}
                    className="px-4 py-2 bg-accent text-background rounded-lg hover:bg-accent/90 transition-colors font-medium text-sm"
                >
                    {action.label}
                </button>
            )}
        </div>
    )
}
