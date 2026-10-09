'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/lib/api'

export interface AsyncState<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** Loads data from the API with explicit loading / error states (never substitutes sample data). */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const seq = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)

  useEffect(() => {
    const id = ++seq.current
    setLoading(true)
    setError(null)
    run().then(
      (d) => { if (id === seq.current) { setData(d); setLoading(false) } },
      (e) => { if (id === seq.current) { setError(e instanceof ApiError ? e.message : 'Request failed'); setLoading(false) } },
    )
  }, [run, tick])

  return { data, error, loading, reload: () => setTick((t) => t + 1) }
}
