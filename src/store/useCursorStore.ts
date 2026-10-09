import { create } from 'zustand'

/** High-frequency cursor/camera readout kept out of the main store so mouse moves do not re-render the app. */
interface CursorState {
  lon: number | null
  lat: number | null
  zoom: number | null
  scaleLabel: string | null
  set: (p: Partial<Omit<CursorState, 'set'>>) => void
}
export const useCursorStore = create<CursorState>((set) => ({ lon: null, lat: null, zoom: null, scaleLabel: null, set: (p) => set(p) }))
