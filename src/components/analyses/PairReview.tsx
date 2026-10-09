'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, Ban, CheckCircle2, Columns2, Info, Play } from 'lucide-react'
import { api, ApiError, type DetectionMethod, type ImageryAsset, type PairValidation } from '@/lib/api'
import { cn, formatPct } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, Field, inputCls, Spinner } from '@/components/ui/kit'

interface Props {
  projectId: string
  before: ImageryAsset
  after: ImageryAsset
  inputType: 'upload' | 'sentinel'
  acquisitionParams?: Record<string, unknown>
  /** Open the slider comparison as soon as the pair validates (upload flow). */
  autoCompare?: boolean
}

const METHODS: { id: DetectionMethod; label: string; desc: string }[] = [
  { id: 'auto', label: 'Automatic', desc: 'Picks the learned model for RGB imagery at 0.25-4 m when installed, otherwise the spectral baseline.' },
  { id: 'spectral_cva', label: 'Spectral baseline', desc: 'Robust change-vector analysis over all common bands with radiometric normalisation. Works for any sensor; no training data needed.' },
  { id: 'ndvi_diff', label: 'NDVI difference', desc: 'Vegetation change from red + NIR bands. Only available when both bands exist.' },
  { id: 'learned_siamese', label: 'Learned model (Siamese ResNet50-UNet)', desc: 'Trained on building change in 0.5-1 m aerial imagery.' },
]

export default function PairReview({ projectId, before, after, inputType, acquisitionParams, autoCompare = false }: Props) {
  const router = useRouter()
  const system = useAppStore((s) => s.system)
  const upsert = useAppStore((s) => s.upsertAnalysis)
  const setActive = useAppStore((s) => s.setActiveAnalysis)
  const setDrawerTab = useAppStore((s) => s.setDrawerTab)
  const toast = useAppStore((s) => s.toast)
  const setQuick = useAppStore((s) => s.setQuickCompare)
  const setViewMode = useAppStore((s) => s.setViewMode)
  const requestFly = useAppStore((s) => s.requestFly)
  const [comparing, setComparing] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)
  const autoDone = useRef<string | null>(null)

  const [validation, setValidation] = useState<PairValidation | null>(null)
  const [vError, setVError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [method, setMethod] = useState<DetectionMethod>('auto')
  const [sigmaK, setSigmaK] = useState(4)
  const [minArea, setMinArea] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true); setVError(null); setConfirmed(false)
    api.imagery.validatePair({ before_asset_id: before.id, after_asset_id: after.id })
      .then((v) => alive && setValidation(v))
      .catch((e) => alive && setVError(e instanceof ApiError ? e.message : 'Validation failed'))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [before.id, after.id, before.band_map, after.band_map])

  const roles = validation?.bands.common_roles ?? []
  const hasNdvi = roles.includes('red') && roles.includes('nir')
  const model = system?.ml.models.find((m) => m.id === system.ml.default_model)
  const errors = validation?.issues.filter((i) => i.level === 'error') ?? []
  const warnings = validation?.issues.filter((i) => i.level === 'warning') ?? []
  const infos = validation?.issues.filter((i) => i.level === 'info') ?? []
  const fraction = (validation?.overlap?.fraction_of_before as number | undefined) ?? null
  const coarse = (validation?.suggested_pixel_size_m ?? 0) > 4
  const needsConfirm = warnings.length > 0
  const canRun = !!validation?.ok && !busy && (!needsConfirm || confirmed) && !(method === 'ndvi_diff' && !hasNdvi) && !(method === 'learned_siamese' && !validation.model_available)

  const config = useMemo(() => ({
    detection: { method, sigma_k: sigmaK },
    ...(minArea ? { postprocess: { min_area_m2: Number(minArea) } } : {}),
  }), [method, sigmaK, minArea])

  async function run() {
    setBusy(true)
    try {
      const a = await api.analyses.create({
        project_id: projectId, before_asset_id: before.id, after_asset_id: after.id, name: name || undefined, config, input_type: inputType,
        acquisition_params: acquisitionParams,
      })
      upsert(a)
      setActive(a.id)
      setDrawerTab('progress')
      toast('info', 'Analysis queued. Progress is shown in the drawer.')
      router.push('/map')
    } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Could not start the analysis') } finally { setBusy(false) }
  }

  /** Show both uploaded images over their common area, side by side / with the slider (ML changes are one switch away). */
  async function compareNow() {
    const bb = validation?.overlap?.bounds_wgs84 as number[] | undefined
    if (!bb || bb.length !== 4) { toast('error', 'The two images do not share a common area to compare.'); return }
    const bbox = bb as [number, number, number, number]
    setComparing(true); setCompareError(null)
    const urls: string[] = []
    try {
      for (const a of [before, after]) urls.push(await api.imagery.renderPng(a.id, bbox, 1536))
      setQuick({
        bbox,
        before: { url: urls[0], date: before.acquisition_start ?? '', cloud: null, productId: before.id, label: before.original_filename ?? 'Before' },
        after: { url: urls[1], date: after.acquisition_start ?? '', cloud: null, productId: after.id, label: after.original_filename ?? 'After' },
        source: { kind: 'upload', beforeAssetId: before.id, afterAssetId: after.id, projectId },
      })
      setActive(null)
      setViewMode('compare')
      requestFly({ bbox })
      router.push('/map')
    } catch (e) {
      urls.forEach((u) => URL.revokeObjectURL(u))
      const msg = e instanceof ApiError ? e.message : 'Could not render the images.'
      setCompareError(msg)
      toast('error', msg)
    } finally { setComparing(false) }
  }

  // upload flow: as soon as both images are in and the pair validates, show them side by side with the slider
  useEffect(() => {
    if (!autoCompare || !validation?.ok) return
    const key = `${before.id}:${after.id}`
    if (autoDone.current === key) return
    autoDone.current = key
    void compareNow()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoCompare, validation, before.id, after.id])

  if (loading && !validation) return <div role="status" className="flex items-center gap-2 py-6 text-xs text-slate-400"><Spinner /> Validating the pair...</div>
  if (vError) return <p role="alert" className="rounded border border-red-500/30 bg-red-500/[0.07] p-3 text-xs text-red-300">{vError}</p>
  if (!validation) return null

  return (
    <div className="space-y-4">
      {(comparing || compareError) && (
        <div role={compareError ? 'alert' : 'status'} className={cn('flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-xs', compareError ? 'border-red-500/30 bg-red-500/[0.07] text-red-300' : 'border-accent/30 bg-accent/[0.06] text-slate-200')}>
          {compareError ? <span>Could not open the comparison: {compareError}</span> : <span className="flex items-center gap-2"><Spinner /> Rendering both images side by side…</span>}
          {compareError && <Button tone="ghost" onClick={() => void compareNow()}>Try again</Button>}
        </div>
      )}
      <div className="rounded-md border border-white/[0.07] bg-black/20 p-3">
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-200">
          {validation.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden /> : <Ban className="h-4 w-4 text-red-400" aria-hidden />}
          {validation.ok ? 'Pair is compatible' : 'Pair cannot be processed'}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-2xs text-slate-400 md:grid-cols-4">
          <div><dt>Overlap</dt><dd className="text-slate-200">{fraction !== null ? formatPct(fraction, 0) : '-'} of before</dd></div>
          <div><dt>Analysis CRS</dt><dd className="text-slate-200">{validation.analysis_crs_epsg ? `EPSG:${validation.analysis_crs_epsg}` : '-'}</dd></div>
          <div><dt>Working resolution</dt><dd className="text-slate-200">{validation.suggested_pixel_size_m?.toFixed(2)} m</dd></div>
          <div><dt>Common bands</dt><dd className="text-slate-200">{roles.join(', ') || '-'}</dd></div>
        </dl>
        <ul className="mt-3 space-y-1.5">
          {errors.map((i, k) => <li key={`e${k}`} className="flex gap-1.5 text-xs text-red-300"><Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{i.message}</li>)}
          {warnings.map((i, k) => <li key={`w${k}`} className="flex gap-1.5 text-xs text-amber-200"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{i.message}</li>)}
          {infos.map((i, k) => <li key={`i${k}`} className="flex gap-1.5 text-xs text-slate-500"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{i.message}</li>)}
        </ul>
        <p className="mt-2 text-2xs text-slate-500">Cloud, shadow and haze are only masked when a Sentinel-2 scene-classification band is present; otherwise contamination is not assessed.</p>
      </div>

      {validation.ok && (
        <>
          <fieldset className="space-y-2">
            <legend className="label mb-1">Detection method</legend>
            {METHODS.map((m) => {
              const disabled = (m.id === 'ndvi_diff' && !hasNdvi) || (m.id === 'learned_siamese' && !validation.model_available)
              return (
                <label key={m.id} className={cn('flex cursor-pointer gap-2.5 rounded-md border p-2.5 transition-colors', method === m.id ? 'border-accent/40 bg-accent/[0.06]' : 'border-white/[0.07] hover:bg-white/[0.03]', disabled && 'cursor-not-allowed opacity-45')}>
                  <input type="radio" name="method" className="mt-0.5" checked={method === m.id} disabled={disabled} onChange={() => setMethod(m.id)} />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 text-xs text-slate-100">{m.label}{m.id === 'auto' && <Chip tone="accent">suggests: {validation.suggested_method.replace(/_/g, ' ')}</Chip>}{disabled && <Chip tone="warn">{m.id === 'ndvi_diff' ? 'needs red + NIR' : 'not installed'}</Chip>}</span>
                    <span className="mt-0.5 block text-2xs text-slate-500">{m.desc}</span>
                    {m.id === 'auto' && <span className="mt-0.5 block text-2xs text-slate-500">{validation.suggested_method_reason}</span>}
                  </span>
                </label>
              )
            })}
          </fieldset>

          {(method === 'learned_siamese' || (method === 'auto' && validation.suggested_method === 'learned_siamese')) && model && (
            <div className="rounded-md border border-white/[0.07] p-2.5 text-2xs text-slate-400">
              <div className="text-xs text-slate-200">{model.name}</div>
              {model.metrics.test && <p className="mt-1">Held-out benchmark on its own dataset: F1 {model.metrics.test.f1.toFixed(2)}, precision {model.metrics.test.precision.toFixed(2)}, recall {model.metrics.test.recall.toFixed(2)} ({model.metrics.test.num_samples} samples). This is not a measurement of accuracy on your imagery.</p>}
              <ul className="mt-1 list-disc pl-4 text-amber-200/80">{model.limitations.slice(0, 3).map((l) => <li key={l}>{l}</li>)}</ul>
              {coarse && <p className="mt-1 text-amber-300">Your working resolution ({validation.suggested_pixel_size_m?.toFixed(1)} m) is far from what this model was trained on. Prefer the spectral baseline.</p>}
            </div>
          )}

          <details className="rounded-md border border-white/[0.07] p-2.5">
            <summary className="cursor-pointer text-xs text-slate-300">Advanced options</summary>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <Field label={`Sensitivity (threshold = ${sigmaK} robust sigma)`} hint="Lower finds more, fainter change (and more false positives). Applies to the spectral baseline.">
                <input type="range" min={2} max={8} step={0.5} value={sigmaK} onChange={(e) => setSigmaK(Number(e.target.value))} aria-label="Threshold in robust sigma" className="w-full" />
              </Field>
              <Field label="Minimum change area (m2)" htmlFor="minarea" hint="Default: 4 pixels. Raise it to ignore small features.">
                <input id="minarea" type="number" min={0} value={minArea} onChange={(e) => setMinArea(e.target.value)} placeholder="auto" className={inputCls} />
              </Field>
            </div>
          </details>

          <Field label="Analysis name (optional)" htmlFor="aname"><input id="aname" value={name} maxLength={160} onChange={(e) => setName(e.target.value)} placeholder="e.g. Harbour expansion 2024" className={inputCls} /></Field>
          {needsConfirm && (
            <label className="flex items-start gap-2 text-xs text-amber-100"><input type="checkbox" className="mt-0.5" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I have read the warnings above and want to process this pair anyway.</label>
          )}
        </>
      )}
      <Button className="w-full py-2" disabled={!validation?.ok || comparing} loading={comparing} onClick={() => void compareNow()} title="Show both images over their common area with the slider; turn on ML changes there"><Columns2 className="h-3.5 w-3.5" aria-hidden /> Compare side by side (with ML changes)</Button>
      <Button tone="accent" className="w-full py-2" disabled={!canRun} loading={busy} onClick={run}><Play className="h-3.5 w-3.5" aria-hidden /> Run change detection</Button>
    </div>
  )
}
