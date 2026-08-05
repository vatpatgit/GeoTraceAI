'use client'

import React from 'react'

interface CardProps {
    children: React.ReactNode
    header?: React.ReactNode
    footer?: React.ReactNode
    onClick?: () => void
    hoverable?: boolean
    className?: string
}

export default function Card({
    children,
    header,
    footer,
    onClick,
    hoverable = false,
    className = '',
}: CardProps) {
    return (
        <div
            onClick={onClick}
            className={`bg-slate-800 border border-slate-700 rounded-lg overflow-hidden ${hoverable && onClick ? 'cursor-pointer hover:border-accent/40 transition-colors' : ''
                } ${className}`}
        >
            {header && (
                <div className="px-6 py-4 border-b border-slate-700">
                    {header}
                </div>
            )}

            <div className="px-6 py-4">
                {children}
            </div>

            {footer && (
                <div className="px-6 py-4 border-t border-slate-700 bg-slate-900/20">
                    {footer}
                </div>
            )}
        </div>
    )
}
