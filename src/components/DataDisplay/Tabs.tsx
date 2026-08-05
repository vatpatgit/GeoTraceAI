'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'

interface Tab {
    id: string
    label: string
    content: React.ReactNode
    icon?: React.ReactNode
}

interface TabsProps {
    tabs: Tab[]
    defaultTab?: string
}

export default function Tabs({ tabs, defaultTab }: TabsProps) {
    const [activeTab, setActiveTab] = useState(defaultTab || tabs[0]?.id || '')

    const activeTabData = tabs.find(t => t.id === activeTab)

    return (
        <div className="w-full">
            {/* Tab List */}
            <div className="flex border-b border-slate-700 bg-slate-900/20">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`relative flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${activeTab === tab.id
                                ? 'text-accent'
                                : 'text-slate-400 hover:text-slate-300'
                            }`}
                    >
                        {tab.icon}
                        {tab.label}
                        {activeTab === tab.id && (
                            <motion.div
                                layoutId="tab-underline"
                                className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent"
                                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                            />
                        )}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="pt-4"
            >
                {activeTabData?.content}
            </motion.div>
        </div>
    )
}
