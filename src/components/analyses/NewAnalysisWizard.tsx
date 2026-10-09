'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Satellite, Upload } from 'lucide-react'
import { canWrite } from '@/lib/auth'
import { cn } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import type { ImageryAsset } from '@/lib/api'
import type { PlainImage } from '@/store/useAppStore'
import { EmptyBlock } from '@/components/ui/kit'
import AssetMap from './AssetMap'
import PairReview from './PairReview'
import UploadSlot from './UploadSlot'
import SentinelStep from './SentinelStep'
import PlainPairStep from './PlainPairStep'

type Source = 'upload' | 'sentinel'

export default function NewAnalysisWizard() {
  const user = useAppStore((s) => s.authUser)
  const projects = useAppStore((s) => s.projects)
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const setActiveProject = useAppStore((s) => s.setActiveProject)
  const system = useAppStore((s) => s.system)
  const [source, setSource] = useState<Source>('upload')
  const [before, setBefore] = useState<ImageryAsset | null>(null)
  const [after, setAfter] = useState<ImageryAsset | null>(null)
  const [beforePlain, setBeforePlain] = useState<PlainImage | null>(null)
  const [afterPlain, setAfterPlain] = useState<PlainImage | null>(null)

  if (!canWrite(user?.role)) {
    return <EmptyBlock title="Your role is read-only" hint="Viewers can explore shared analyses but cannot create new ones." action={<Link href="/map" className="btn border-[color:var(--line-strong)]">Back to the map</Link>} />
  }
  const writable = projects.filter((p) => p.can_write)
  const project = writable.find((p) => p.id === activeProjectId) ?? writable[0]
  if (!project) return <EmptyBlock title="No writable project" hint="Create a project first (Settings, or Analyses)." />

  const sentinelProvider = system?.sentinel[0] ?? null

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-base font-semibold text-slate-100">New analysis</h1>
          <p className="mt-0.5 text-xs text-slate-500">Acquire a before/after pair, confirm it is compatible, then run change detection.</p>
        </div>
        <label className="text-2xs text-slate-500">Project
          <select value={project.id} onChange={(e) => setActiveProject(e.target.value)} aria-label="Project" className="focus-ring ml-2 rounded border border-[color:var(--line-strong)] bg-black/30 px-2 py-1 text-xs text-slate-200">{writable.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        </label>
      </header>

      <div role="tablist" aria-label="Imagery source" className="grid gap-2 md:grid-cols-2">
        {([['upload', 'Upload imagery', 'GeoTIFFs (georeferenced) or ordinary images (PNG, JPG, WebP…) of the same area.', Upload], ['sentinel', 'Search Sentinel-2', sentinelProvider?.imagery === 'available' ? 'Pick an area and two date ranges; GeoTrace retrieves the scenes.' : sentinelProvider?.catalog === 'available' ? 'Catalogue search works; imagery retrieval needs server credentials.' : 'Provider unavailable right now.', Satellite]] as const).map(([id, title, desc, Icon]) => (
          <button key={id} role="tab" aria-selected={source === id} onClick={() => setSource(id)} className={cn('focus-ring flex items-start gap-3 rounded-md border p-3 text-left transition-colors', source === id ? 'border-accent-dim bg-accent/[0.06]' : 'border-[color:var(--line-strong)] hover:bg-ink-800/70')}>
            <Icon className={cn('mt-0.5 h-5 w-5', source === id ? 'text-accent' : 'text-slate-500')} aria-hidden />
            <span><span className="block text-sm text-slate-100">{title}</span><span className="block text-xs text-slate-500">{desc}</span></span>
          </button>
        ))}
      </div>

      {source === 'upload' ? (
        <>
          <section className="grid gap-5 md:grid-cols-2" aria-label="Upload imagery">
            <div className="space-y-3"><UploadSlot title="1. Before image" projectId={project.id} asset={before} onAsset={setBefore} plain={beforePlain} onPlain={setBeforePlain} /><AssetMap assetId={before?.id ?? null} bounds={before?.bounds ?? null} label="Before" /></div>
            <div className="space-y-3"><UploadSlot title="2. After image" projectId={project.id} asset={after} onAsset={setAfter} plain={afterPlain} onPlain={setAfterPlain} /><AssetMap assetId={after?.id ?? null} bounds={after?.bounds ?? null} label="After" /></div>
          </section>
          {(before && afterPlain) || (beforePlain && after) ? (
            <p role="alert" className="rounded border border-amber-400/30 bg-amber-400/[0.06] p-3 text-xs text-amber-100">Use two GeoTIFFs or two ordinary images: a GeoTIFF has coordinates and an ordinary image does not, so the two cannot be compared with each other. Replace one of them.</p>
          ) : beforePlain && afterPlain ? (
            <section aria-label="Image comparison" className="rounded-lg border border-[color:var(--line-strong)] bg-ink-850 p-4">
              <h2 className="label mb-3">3. Compare images</h2>
              <PlainPairStep before={beforePlain} after={afterPlain} />
            </section>
          ) : before && after ? (
            <section aria-label="Review and run" className="rounded-lg border border-[color:var(--line-strong)] bg-ink-850 p-4">
              <h2 className="label mb-3">3. Review compatibility and run</h2>
              <PairReview projectId={project.id} before={before} after={after} inputType="upload" autoCompare />
            </section>
          ) : <p className="text-center text-xs text-slate-600">Upload both images to compare them.</p>}
        </>
      ) : (
        <SentinelStep projectId={project.id} />
      )}
    </div>
  )
}
