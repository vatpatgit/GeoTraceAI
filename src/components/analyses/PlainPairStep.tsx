'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useRef } from 'react'
import { AlertTriangle, Info } from 'lucide-react'
import { useAppStore, type PlainImage } from '@/store/useAppStore'
import { Spinner } from '@/components/ui/kit'

/** Two ordinary images were chosen: compare them (no map, no coordinates) as soon as both are in. */
export default function PlainPairStep({ before, after }: { before: PlainImage; after: PlainImage }) {
  const router = useRouter()
  const setPlain = useAppStore((s) => s.setPlainCompare)
  const opened = useRef<string | null>(null)
  const ratio = (before.width / before.height) / (after.width / after.height)
  const mismatch = Math.abs(ratio - 1) > 0.03

  useEffect(() => {
    if (mismatch) return
    const key = `${before.url}|${after.url}`
    if (opened.current === key) return
    opened.current = key
    setPlain({ before, after })
    router.push('/image-compare')
  }, [before, after, mismatch, setPlain, router])

  if (mismatch) {
    return (
      <p role="alert" className="flex gap-2 rounded border border-red-500/30 bg-red-500/[0.07] p-3 text-xs text-red-300">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        The images have different proportions ({before.width}x{before.height} vs {after.width}x{after.height}). They must show the same area framed the same way: replace one of them.
      </p>
    )
  }
  return (
    <div role="status" className="space-y-1.5 text-xs text-slate-300">
      <div className="flex items-center gap-2"><Spinner /> Opening the side-by-side comparison…</div>
      <p className="flex gap-1.5 text-2xs text-slate-500"><Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />Ordinary images carry no coordinates, so they are compared without a map and assumed to show the same area, framed identically.</p>
    </div>
  )
}
