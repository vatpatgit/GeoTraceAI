'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { GitCompare, MapPin, Plus, Trash2 } from 'lucide-react'
import { api, apiFetch, ApiError, type Region } from '@/lib/api'
import { canWrite, isAdmin } from '@/lib/auth'
import { cn, formatDate } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, EmptyBlock, Field, inputCls } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'

const RISKS = ['low', 'medium', 'high', 'critical']

function bboxOf(r: Region): [number, number, number, number] | null {
  const g = r.geometry as { coordinates?: number[][][] | number[][][][] } | null
  if (!g?.coordinates) return null
  const pts: number[][] = []
  const walk = (c: unknown): void => { if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[]); else if (Array.isArray(c)) c.forEach(walk) }
  walk(g.coordinates)
  if (!pts.length) return null
  const xs = pts.map((p) => p[0]); const ys = pts.map((p) => p[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]
}

export default function RegionsPage() {
  const router = useRouter()
  const regions = useAppStore((s) => s.regions)
  const setRegions = useAppStore((s) => s.setRegions)
  const requestFly = useAppStore((s) => s.requestFly)
  const user = useAppStore((s) => s.authUser)
  const toast = useAppStore((s) => s.toast)
  const admin = isAdmin(user?.role)
  const writer = canWrite(user?.role)
  const setQuickPrefill = useAppStore((s) => s.setQuickPrefill)
  const setLeftPanel = useAppStore((s) => s.setLeftPanel)
  const [form, setForm] = useState({ name: '', description: '', risk: 'medium', west: '', south: '', east: '', north: '' })
  const [busy, setBusy] = useState(false)

  const nums = [form.west, form.south, form.east, form.north].map(Number)
  const bboxError =
    [form.west, form.south, form.east, form.north].some((v) => v.trim() === '') || nums.some((n) => !Number.isFinite(n)) ? 'Enter all four bounds as numbers.'
    : nums[0] < -180 || nums[2] > 180 || nums[1] < -90 || nums[3] > 90 ? 'Longitudes must be within ±180 and latitudes within ±90.'
    : nums[0] >= nums[2] || nums[1] >= nums[3] ? 'West must be less than east and south less than north.' : null

  async function create() {
    if (bboxError || !form.name.trim()) return
    const [w, s, e, n] = nums
    setBusy(true)
    try {
      await apiFetch('/regions/', { method: 'POST', body: { name: form.name.trim(), description: form.description.trim() || null, risk_level: form.risk, geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } } })
      setRegions(await api.regions.list())
      setForm({ name: '', description: '', risk: 'medium', west: '', south: '', east: '', north: '' })
      toast('success', 'Region created')
    } catch (err) { toast('error', err instanceof ApiError ? err.message : 'Could not create region') } finally { setBusy(false) }
  }

  async function remove(r: Region) {
    if (!window.confirm(`Delete region "${r.name}"? Alert rules scoped to it will stop matching.`)) return
    try { await apiFetch(`/regions/${r.id}`, { method: 'DELETE' }); setRegions(regions.filter((x) => x.id !== r.id)); toast('success', 'Region deleted') }
    catch (err) { toast('error', err instanceof ApiError ? err.message : 'Could not delete region') }
  }

  return (
    <PageFrame title="Monitored regions" subtitle="Boundaries that scope alert rules and drive the “distance to boundary” attribute stored with each detection.">
      <Card title={`Regions (${regions.length})`}>
        {regions.length === 0 ? <EmptyBlock title="No monitored regions" hint={admin ? 'Add one below.' : 'An administrator can define monitored regions.'} /> : (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500"><tr><th className="label py-1.5 font-normal">Name</th><th className="label font-normal">Risk level</th><th className="label text-right font-normal">Area</th><th className="label pl-4 font-normal">Created</th><th /></tr></thead>
            <tbody>
              {regions.map((r) => (
                <tr key={r.id} className="border-t border-[color:var(--line)]">
                  <td className="py-2"><div className="text-slate-100">{r.name}</div>{r.description && <div className="text-2xs text-slate-500">{r.description}</div>}</td>
                  <td><Chip tone={r.risk_level === 'critical' || r.risk_level === 'high' ? 'danger' : r.risk_level === 'medium' ? 'warn' : 'default'} title="Configured by an administrator; not computed from imagery.">{r.risk_level}</Chip></td>
                  <td className="text-right font-mono text-slate-300">{r.area_km2.toLocaleString(undefined, { maximumFractionDigits: 1 })} km²</td>
                  <td className="pl-4 text-2xs text-slate-500">{formatDate(r.created_at)}</td>
                  <td className="space-x-1 text-right">
                    <Button tone="ghost" aria-label={`Show ${r.name} on the map`} onClick={() => { const b = bboxOf(r); requestFly(b ? { bbox: b } : { center: [r.center_lng, r.center_lat], zoom: 8 }); router.push('/map') }}><MapPin className="h-3.5 w-3.5" aria-hidden /> Map</Button>
                    {writer && <Button tone="ghost" aria-label={`Compare ${r.name} over time`} onClick={() => { const b = bboxOf(r); if (!b) return; setQuickPrefill({ name: r.name, bbox: b }); setLeftPanel('quick'); router.push('/map') }}><GitCompare className="h-3.5 w-3.5" aria-hidden /> Compare dates</Button>}
                    {admin && <Button tone="ghost" aria-label={`Delete ${r.name}`} onClick={() => void remove(r)}><Trash2 className="h-3.5 w-3.5" aria-hidden /></Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {admin && (
        <Card title="Add a region (bounding box)">
          <form className="grid gap-3 md:grid-cols-4" onSubmit={(e) => { e.preventDefault(); void create() }}>
            <Field label="Name" htmlFor="rg-name"><input id="rg-name" className={inputCls} value={form.name} maxLength={120} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Risk level (configured)" htmlFor="rg-risk"><select id="rg-risk" className={inputCls} value={form.risk} onChange={(e) => setForm({ ...form, risk: e.target.value })}>{RISKS.map((r) => <option key={r}>{r}</option>)}</select></Field>
            <div className="md:col-span-2"><Field label="Description" htmlFor="rg-desc"><input id="rg-desc" className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
            {(['west', 'south', 'east', 'north'] as const).map((k) => (
              <Field key={k} label={`${k} (${k === 'west' || k === 'east' ? 'lon' : 'lat'})`} htmlFor={`rg-${k}`}>
                <input id={`rg-${k}`} inputMode="decimal" className={cn(inputCls, 'font-mono')} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </Field>
            ))}
            <div className="flex items-center gap-3 md:col-span-4">
              <Button type="submit" tone="accent" loading={busy} disabled={!!bboxError || !form.name.trim()}><Plus className="h-3.5 w-3.5" aria-hidden /> Create region</Button>
              {bboxError && form.west + form.south + form.east + form.north !== '' && <span className="text-2xs text-amber-300">{bboxError}</span>}
            </div>
          </form>
        </Card>
      )}
    </PageFrame>
  )
}
