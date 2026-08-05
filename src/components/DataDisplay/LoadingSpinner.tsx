'use client'

interface LoadingSpinnerProps {
    size?: 'sm' | 'md' | 'lg'
    message?: string
}

export default function LoadingSpinner({ size = 'md', message }: LoadingSpinnerProps) {
    const sizeClass = {
        sm: 'w-6 h-6',
        md: 'w-8 h-8',
        lg: 'w-12 h-12',
    }[size]

    return (
        <div className="flex flex-col items-center justify-center gap-3">
            <div className={`${sizeClass} border-2 border-accent border-t-transparent rounded-full animate-spin`} />
            {message && <p className="text-sm text-slate-400">{message}</p>}
        </div>
    )
}
