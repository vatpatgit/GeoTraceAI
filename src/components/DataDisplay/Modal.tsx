'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'

interface ModalProps {
    isOpen: boolean
    onClose: () => void
    title?: string
    children: React.ReactNode
    actions?: {
        label: string
        onClick: () => void
        variant?: 'primary' | 'danger' | 'secondary'
    }[]
    size?: 'sm' | 'md' | 'lg'
}

export default function Modal({
    isOpen,
    onClose,
    title,
    children,
    actions,
    size = 'md',
}: ModalProps) {
    const sizeClass = {
        sm: 'w-96',
        md: 'w-[32rem]',
        lg: 'w-[48rem]',
    }[size]

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/50 z-40"
                    />

                    {/* Modal */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 20 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 20 }}
                        onClick={(e) => e.stopPropagation()}
                        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 ${sizeClass} bg-slate-800 border border-slate-700 rounded-lg shadow-xl`}
                    >
                        {/* Header */}
                        {title && (
                            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
                                <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
                                <button
                                    onClick={onClose}
                                    className="text-slate-400 hover:text-slate-200 transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>
                        )}

                        {/* Body */}
                        <div className="px-6 py-4">{children}</div>

                        {/* Footer */}
                        {actions && actions.length > 0 && (
                            <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-slate-700">
                                {actions.map((action, idx) => {
                                    const variantClass = {
                                        primary: 'bg-accent hover:bg-accent/80 text-black',
                                        danger: 'bg-red-600 hover:bg-red-700 text-white',
                                        secondary: 'bg-slate-700 hover:bg-slate-600 text-slate-100',
                                    }[action.variant || 'secondary']

                                    return (
                                        <button
                                            key={idx}
                                            onClick={action.onClick}
                                            className={`px-4 py-2 rounded font-medium transition-colors ${variantClass}`}
                                        >
                                            {action.label}
                                        </button>
                                    )
                                })}
                            </div>
                        )}
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    )
}
