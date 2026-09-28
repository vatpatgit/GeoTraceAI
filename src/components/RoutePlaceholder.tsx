'use client'

import Link from 'next/link'
import { ArrowLeft, Construction } from 'lucide-react'
import CollapsibleSidebar from './Layout/CollapsibleSidebar'
import Header from './Header'

interface RoutePlaceholderProps {
    title: string
    description: string
}

export default function RoutePlaceholder({ title, description }: RoutePlaceholderProps) {
    return (
        <div className="min-h-screen bg-background text-white flex">
            <CollapsibleSidebar />
            <main className="flex-1 min-w-0">
                <Header />
                <section className="max-w-3xl mx-auto px-6 py-16">
                    <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-accent">
                        <ArrowLeft className="w-4 h-4" /> Back to dashboard
                    </Link>
                    <div className="mt-12 glass-card rounded-xl border border-white/10 p-8">
                        <Construction className="w-8 h-8 text-accent" />
                        <h1 className="mt-5 text-3xl font-semibold">{title}</h1>
                        <p className="mt-3 text-slate-400">{description}</p>
                    </div>
                </section>
            </main>
        </div>
    )
}
