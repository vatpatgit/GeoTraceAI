import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  try {
    window.localStorage.clear()
  } catch {
    /* jsdom without storage */
  }
})

// jsdom lacks ResizeObserver (used by Recharts' ResponsiveContainer); a no-op stub is enough for logic tests.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}
