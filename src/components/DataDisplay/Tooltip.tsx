'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface TooltipProps {
    content: string
    position?: 'top' | 'bottom' | 'left' | 'right'
    children: React.ReactNode
    delay?: number
}

export default function Tooltip({ content, position = 'top', children, delay = 200 }: TooltipProps) {
    const [isVisible, setIsVisible] = useState(false)

    const positionClass = {
        top: 'bottom-full mb-2 left-1/2 -translate-x-1/2',
        bottom: 'top-full mt-2 left-1/2 -translate-x-1/2',
        left: 'right-full mr-2 top-1/2 -translate-y-1/2',
        right: 'left-full ml-2 top-1/2 -translate-y-1/2',
    }[position]

    const arrowClass = {
        top: 'bottom-0 left-1/2 -translate-x-1/2 translate-y-full border-t-slate-700',
        bottom: 'top-0 left-1/2 -translate-x-1/2 -translate-y-full border-b-slate-700',
        left: 'left-0 top-1/2 -translate-y-1/2 -translate-x-full border-l-slate-700',
        right: 'right-0 top-1/2 -translate-y-1/2 translate-x-full border-r-slate-700',
    }[position]

    return (
        <div className="relative inline-block">
            <div
                onMouseEnter={() => setTimeout(() => setIsVisible(true), delay)}
                onMouseLeave={() => setIsVisible(false)}
                className="cursor-help"
            >
                {children}
            </div>
            <AnimatePresence>
                {isVisible && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        transition={{ duration: 0.15 }}
                        className={`absolute ${positionClass} z-50 pointer-events-none`}
                    >
                        <div className="relative">
                            <div className="px-2.5 py-1.5 bg-slate-700 text-slate-100 text-xs rounded whitespace-nowrap shadow-lg">
                                {content}
                            </div>
                            <div
                                className={`absolute w-0 h-0 border-4 border-transparent ${arrowClass}`}
                            />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}
