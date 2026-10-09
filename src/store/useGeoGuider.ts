import { create } from 'zustand'
import { api, ApiError } from '@/lib/api'
import type { GgAction, GgMessage, GgStatus, GgUi, GgWorkflow } from '@/lib/api/geoguider'

const KEY = 'geoguider_conversation_id'
const read = (): string | null => { try { return window.sessionStorage.getItem(KEY) } catch { return null } }
const write = (v: string | null) => { try { if (v) window.sessionStorage.setItem(KEY, v); else window.sessionStorage.removeItem(KEY) } catch { /* private mode */ } }

export const WELCOME = "Hi, I'm GeoGuider, your AI geospatial copilot. Tell me what you want to investigate, and I'll help you find the right data, run supported GeoTraceAI analyses, visualize the results, and understand what they reveal."

type Sent = { message?: string; choice?: { pending_id: string; option_id: string }; ui: GgUi }

interface GgStore {
  open: boolean
  conversationId: string | null
  messages: GgMessage[]
  workflow: GgWorkflow | null
  suggestions: string[]
  status: GgStatus | null
  busy: boolean
  error: string | null
  lastSent: Sent | null
  setOpen: (v: boolean) => void
  loadStatus: () => Promise<void>
  restore: () => Promise<void>
  send: (message: string, ui: GgUi) => Promise<GgAction[]>
  choose: (pendingId: string, optionId: string, ui: GgUi) => Promise<GgAction[]>
  retry: () => Promise<GgAction[]>
  poll: () => Promise<GgAction[]>
  cancel: () => Promise<GgAction[]>
  reset: () => void
}

const localMsg = (role: 'user' | 'assistant', content: string): GgMessage => ({ id: `local-${Math.random().toString(36).slice(2)}`, role, content, blocks: [], actions: [], created_at: new Date().toISOString() })
const lastActions = (m: GgMessage[]): GgAction[] => m.filter((x) => x.role === 'assistant').flatMap((x) => x.actions)
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')

export const useGeoGuider = create<GgStore>((set, get) => ({
  open: false, conversationId: null, messages: [], workflow: null, suggestions: [], status: null, busy: false, error: null, lastSent: null,
  setOpen: (open) => set({ open }),
  loadStatus: async () => {
    try { set({ status: await api.geoguider.status() }) } catch { set({ status: null }) }
  },
  restore: async () => {
    const id = read()
    if (!id || get().conversationId) return
    try {
      const c = await api.geoguider.conversation(id)
      set({ conversationId: c.id, messages: c.messages, workflow: c.workflow })
    } catch { write(null) } // expired or not ours: start clean
  },
  send: async (message, ui) => {
    const text = message.trim()
    if (!text || get().busy) return []
    const sent: Sent = { message: text, ui }
    set((s) => ({ busy: true, error: null, lastSent: sent, messages: [...s.messages, localMsg('user', text)] }))
    return run(sent, set, get, true)
  },
  choose: async (pendingId, optionId, ui) => {
    if (get().busy) return []
    const sent: Sent = { choice: { pending_id: pendingId, option_id: optionId }, ui }
    set({ busy: true, error: null, lastSent: sent })
    return run(sent, set, get, false)
  },
  retry: async () => {
    const sent = get().lastSent
    if (!sent || get().busy) return []
    set({ busy: true, error: null })
    return run(sent, set, get, false)
  },
  poll: async () => {
    const id = get().conversationId
    if (!id) return []
    try {
      const r = await api.geoguider.workflow(id)
      set((s) => ({ workflow: r.workflow, messages: r.new_messages.length ? [...s.messages, ...r.new_messages] : s.messages }))
      return lastActions(r.new_messages)
    } catch { return [] } // transient; the next poll retries
  },
  cancel: async () => {
    const id = get().conversationId
    if (!id) return []
    set({ busy: true, error: null })
    try {
      const r = await api.geoguider.cancel(id)
      set((s) => ({ busy: false, workflow: r.workflow, messages: [...s.messages, ...r.messages.filter((m) => m.role === 'assistant')] }))
      return lastActions(r.messages)
    } catch (e) { set({ busy: false, error: errText(e) }); return [] }
  },
  reset: () => { write(null); set({ conversationId: null, messages: [], workflow: null, suggestions: [], error: null, lastSent: null, busy: false }) },
}))

async function run(sent: Sent, set: (p: Partial<GgStore> | ((s: GgStore) => Partial<GgStore>)) => void, get: () => GgStore, userEchoed: boolean): Promise<GgAction[]> {
  try {
    const r = await api.geoguider.chat({ conversation_id: get().conversationId, message: sent.message, choice: sent.choice, ui: sent.ui })
    write(r.conversation_id)
    set((s) => {
      // the optimistic local user bubble is replaced by the stored one
      const base = userEchoed ? s.messages.filter((m) => !m.id.startsWith('local-')) : s.messages
      return { busy: false, conversationId: r.conversation_id, workflow: r.workflow, suggestions: r.suggestions, messages: [...base, ...r.messages] }
    })
    return lastActions(r.messages)
  } catch (e) {
    set({ busy: false, error: errText(e) })
    return []
  }
}
