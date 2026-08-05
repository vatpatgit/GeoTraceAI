'use client'

import React from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

interface ErrorBoundaryProps {
    children: React.ReactNode
    fallback?: (error: Error, retry: () => void) => React.ReactNode
}

interface ErrorBoundaryState {
    hasError: boolean
    error: Error | null
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props)
        this.state = { hasError: false, error: null }
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error }
    }

    componentDidCatch(error: Error) {
        console.error('Error boundary caught:', error)
    }

    retry = () => {
        this.setState({ hasError: false, error: null })
    }

    render() {
        if (this.state.hasError && this.state.error) {
            if (this.props.fallback) {
                return this.props.fallback(this.state.error, this.retry)
            }

            return (
                <div className="flex flex-col items-center justify-center gap-4 p-8 bg-red-950/20 border border-red-900/40 rounded-lg">
                    <div className="flex items-center gap-2 text-red-400">
                        <AlertTriangle size={20} />
                        <span className="font-semibold">Something went wrong</span>
                    </div>
                    <p className="text-sm text-slate-400 text-center">{this.state.error.message}</p>
                    <button
                        onClick={this.retry}
                        className="flex items-center gap-2 px-3 py-1.5 bg-accent hover:bg-accent/80 text-black rounded text-sm font-medium transition-colors"
                    >
                        <RotateCcw size={16} />
                        Try again
                    </button>
                </div>
            )
        }

        return this.props.children
    }
}
