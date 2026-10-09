'use client'

import { useRouter } from 'next/navigation'
import { LogOut } from 'lucide-react'
import { api } from '@/lib/api'
import { roleLabel } from '@/lib/auth'
import { formatPct } from '@/lib/format'
import { useAppStore } from '@/store/useAppStore'
import { Button, Chip, ErrorBlock, Stat } from '@/components/ui/kit'
import PageFrame, { Card } from './PageFrame'

const yes = (ok: boolean, good = 'OK', bad = 'Unavailable') => <Chip tone={ok ? 'ok' : 'danger'}>{ok ? good : bad}</Chip>

export default function SettingsPage() {
  const router = useRouter()
  const user = useAppStore((s) => s.authUser)
  const sys = useAppStore((s) => s.system)
  const err = useAppStore((s) => s.systemError)
  const signOut = useAppStore((s) => s.signOut)

  return (
    <PageFrame title="Settings & system status" subtitle="Read-only status of this deployment. Credentials and API keys live in server-side environment variables and are never shown or stored in the browser.">
      <Card title="Your account">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="Name" value={user?.name ?? '-'} />
          <Stat label="Email" value={user?.email ?? '-'} />
          <Stat label="Role" value={user ? roleLabel[user.role] : '-'} sub={user?.role === 'viewer' ? 'read-only' : undefined} />
          <div className="flex items-end"><Button tone="danger" onClick={() => { api.logout(); signOut(); router.push('/') }}><LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out</Button></div>
        </div>
        <p className="mt-3 text-2xs text-slate-500">The access token is kept in this browser&apos;s local storage until you sign out or it expires.</p>
      </Card>

      {err && <ErrorBlock title="System status unavailable" message={err} />}
      {sys && (
        <>
          <Card title="Platform">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Stat label="Version" value={sys.version} sub={sys.env} />
              <div><div className="label">Database</div><div className="mt-1">{yes(sys.database.ok)}</div>{sys.database.error && <div className="mt-1 text-2xs text-red-300">{sys.database.error}</div>}</div>
              <div><div className="label">Storage</div><div className="mt-1">{yes(sys.storage.ok)}</div></div>
              <Stat label="Job runner" value={sys.job_runner} sub={`${sys.job_concurrency} concurrent`} />
              <div><div className="label">Demo mode</div><div className="mt-1">{sys.demo_mode ? <Chip tone="demo">enabled — demo data is labelled</Chip> : <Chip>off</Chip>}</div></div>
              <Stat label="Max upload" value={`${sys.limits.max_upload_mb} MB`} />
              <Stat label="Max raster" value={`${(sys.limits.max_raster_pixels / 1e6).toFixed(0)} MP`} />
              <Stat label="Max AOI" value={`${sys.limits.max_aoi_km2.toLocaleString()} km²`} />
            </div>
          </Card>

          <Card title="Sentinel-2 acquisition">
            <ul className="space-y-2 text-xs">
              {sys.sentinel.map((p) => (
                <li key={p.provider} className="flex flex-wrap items-center gap-2">
                  <span className="w-44 text-slate-200">{p.provider}</span>{yes(p.configured, 'Credentials configured', 'Credentials not configured')}
                  <span className="text-2xs text-slate-500">{p.detail}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-2xs text-slate-500">Manual GeoTIFF upload works without any provider credentials.</p>
          </Card>

          <Card title="Change-detection models">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span>PyTorch</span>{yes(sys.ml.torch, 'installed', 'not installed')}<span>CUDA</span>{yes(sys.ml.cuda, 'available', 'not available')}<span>Device: <span className="font-mono">{sys.ml.device ?? 'n/a'}</span></span>
            </div>
            {sys.ml.models.length === 0 ? <p className="text-xs text-slate-500">No model cards found. Only the baseline (spectral) detectors are available.</p> : (
              <ul className="space-y-3">
                {sys.ml.models.map((m) => (
                  <li key={m.id} className="rounded-md border border-white/[0.06] p-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-100">{m.name} {yes(m.available, 'weights present', 'weights missing')}<Chip>{m.dataset}</Chip></div>
                    <p className="mt-1 text-2xs text-slate-400">{m.description}</p>
                    {m.metrics.test && <p className="mt-1 font-mono text-2xs text-slate-300">Held-out {m.dataset} test set ({m.metrics.test.num_samples} samples): F1 {formatPct(m.metrics.test.f1)} · IoU {formatPct(m.metrics.test.change_iou)} · P {formatPct(m.metrics.test.precision)} · R {formatPct(m.metrics.test.recall)}</p>}
                    <p className="mt-1 text-2xs text-amber-200/80">{m.metrics_note}</p>
                    <ul className="mt-1 list-disc pl-4 text-2xs text-slate-500">{m.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Analytics language model">
            <div className="flex items-center gap-2 text-xs text-slate-300">{yes(sys.llm.configured, `Configured (${sys.llm.provider})`, 'Not configured')}</div>
            <p className="mt-2 text-2xs text-slate-500">Questions work without a language model (deterministic parsing and wording). When configured, the model only rephrases computed results; wording is discarded if it contains figures that are not in the results.</p>
          </Card>
        </>
      )}
    </PageFrame>
  )
}
