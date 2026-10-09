import type { AnalysisStatus, Severity } from '@/lib/api/types'

export const cn = (...parts: (string | false | null | undefined)[]): string => parts.filter(Boolean).join(' ')

/** Human-friendly area from square metres (never degrees, never km2 mislabelled). */
export function formatArea(m2: number | null | undefined): string {
  if (m2 === null || m2 === undefined || !Number.isFinite(m2)) return '-'
  if (m2 >= 1e6) return `${(m2 / 1e6).toLocaleString('en-US', { maximumFractionDigits: m2 >= 1e7 ? 1 : 2 })} km²`
  if (m2 >= 1e4) return `${(m2 / 1e4).toLocaleString('en-US', { maximumFractionDigits: 1 })} ha`
  return `${Math.round(m2).toLocaleString('en-US')} m²`
}
export const formatM2 = (m2: number | null | undefined): string =>
  m2 === null || m2 === undefined ? '-' : `${Math.round(m2).toLocaleString('en-US')} m²`

export function formatPct(fraction: number | null | undefined, digits = 1): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '-'
  return `${(fraction * 100).toFixed(digits)}%`
}

export function formatDate(iso: string | null | undefined, opts: { time?: boolean } = {}): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  const date = d.toISOString().slice(0, 10)
  return opts.time ? `${date} ${d.toISOString().slice(11, 16)}Z` : date
}

export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '-'
  const diff = (now - new Date(iso).getTime()) / 1000
  if (!Number.isFinite(diff)) return '-'
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`
  if (diff < 86400 * 30) return `${Math.round(diff / 86400)} d ago`
  return formatDate(iso)
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

export function formatCoord(lon: number, lat: number, digits = 5): string {
  const ns = lat >= 0 ? 'N' : 'S'
  const ew = lon >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(digits)}°${ns} ${Math.abs(lon).toFixed(digits)}°${ew}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '-'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

export const toTitle = (s: string): string => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const SEVERITY_COLOR: Record<Severity, string> = { low: '#38BDF8', medium: '#FBBF24', high: '#FB923C', critical: '#F43F5E' }
export const SEVERITY_ORDER: Record<Severity, number> = { low: 0, medium: 1, high: 2, critical: 3 }

export const STATUS_LABEL: Record<AnalysisStatus, string> = {
  queued: 'Queued', validating: 'Validating', acquiring_imagery: 'Acquiring imagery', preprocessing: 'Preprocessing',
  detecting_changes: 'Detecting changes', polygonizing: 'Extracting polygons', evaluating_alerts: 'Evaluating alerts',
  exporting: 'Exporting', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled',
}
export const isActiveStatus = (s: AnalysisStatus): boolean => !['completed', 'failed', 'cancelled'].includes(s)

export const CATEGORY_LABEL: Record<string, string> = {
  unclassified_change: 'Unclassified change', vegetation_decrease: 'Vegetation decrease', vegetation_increase: 'Vegetation increase',
  vegetation_change: 'Vegetation change', building_change: 'Building change (model)', land_cover_change: 'Land-cover change (model)',
}
export const categoryLabel = (c: string): string => CATEGORY_LABEL[c] ?? toTitle(c)

export const BASIS_LABEL: Record<string, string> = {
  observed_difference: 'Observed image difference', spectral_index: 'Spectral-index inference', model_inferred: 'Model-inferred',
}
export const basisLabel = (b: string): string => BASIS_LABEL[b] ?? toTitle(b)
