'use client'

import { useState } from 'react'
import { LogIn } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { toAuthUser, useAppStore } from '@/store/useAppStore'
import { Button, Field, inputCls } from '@/components/ui/kit'
import { Logo } from '@/components/shell/Logo'

export default function LoginScreen() {
  const setAuthUser = useAppStore((s) => s.setAuthUser)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(email.trim(), password)
      setAuthUser(toAuthUser(await api.me()))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed.')
      api.logout()
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-ink-950 p-6">
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-60" style={{ background: 'radial-gradient(60% 50% at 50% 38%, rgba(45,212,191,0.10), transparent 70%)' }} />
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.07]" style={{ backgroundImage: 'linear-gradient(rgba(148,163,184,.6) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,.6) 1px, transparent 1px)', backgroundSize: '48px 48px' }} />
      <form onSubmit={submit} className="panel-solid relative w-full max-w-sm space-y-4 rounded-lg p-6 shadow-2xl shadow-black/60" aria-label="Sign in">
        <div className="flex items-center gap-3">
          <Logo className="h-9 w-9" />
          <div>
            <h1 className="text-base font-semibold tracking-tight text-slate-100">GeoTrace</h1>
            <p className="label">Satellite change intelligence</p>
          </div>
        </div>
        <Field label="Email" htmlFor="email">
          <input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Password" htmlFor="password">
          <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </Field>
        {error && <p role="alert" className="rounded border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-xs text-red-300">{error}</p>}
        <Button type="submit" tone="accent" className="w-full py-2" loading={busy}>
          <LogIn className="h-3.5 w-3.5" aria-hidden /> Sign in
        </Button>
        <p className="text-center text-2xs text-slate-600">Accounts are created by an administrator.</p>
      </form>
    </main>
  )
}
