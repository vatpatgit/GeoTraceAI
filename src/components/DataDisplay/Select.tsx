'use client'

import { useState, useRef, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface SelectOption {
    value: string | number
    label: string
    icon?: React.ReactNode
}

interface SelectProps {
    options: SelectOption[]
    value?: string | number
    onChange: (value: string | number) => void
    placeholder?: string
    label?: string
    icon?: React.ReactNode
}

export default function Select({
    options,
    value,
    onChange,
    placeholder = 'Select an option',
    label,
    icon,
}: SelectProps) {
    const [isOpen, setIsOpen] = useState(false)
    const ref = useRef<HTMLDivElement>(null)

    const selectedOption = options.find(opt => opt.value === value)

    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setIsOpen(false)
            }
        }

        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    return (
        <div ref={ref} className="relative w-full">
            {label && <label className="block text-xs font-medium text-slate-300 mb-2">{label}</label>}

            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between px-3 py-2 bg-slate-700 border border-slate-600 hover:border-slate-500 rounded text-slate-100 text-sm transition-colors"
            >
                <div className="flex items-center gap-2">
                    {icon}
                    <span>{selectedOption?.label || placeholder}</span>
                </div>
                <motion.div animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }}>
                    <ChevronDown size={16} />
                </motion.div>
            </button>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.15 }}
                        className="absolute top-full left-0 right-0 mt-2 z-50 bg-slate-700 border border-slate-600 rounded shadow-lg overflow-hidden"
                    >
                        {options.map((option) => (
                            <button
                                key={option.value}
                                onClick={() => {
                                    onChange(option.value)
                                    setIsOpen(false)
                                }}
                                className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${value === option.value
                                        ? 'bg-accent/20 text-accent'
                                        : 'text-slate-100 hover:bg-slate-600'
                                    }`}
                            >
                                {option.icon}
                                {option.label}
                            </button>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}
