import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GgChatResponse, GgMessage, GgWorkflow } from '@/lib/api/geoguider'
import { useAppStore } from '@/store/useAppStore'
import { useGeoGuider } from '@/store/useGeoGuider'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }), usePathname: () => '/dashboard' }))
const m = vi.hoisted(() => ({ status: vi.fn(), chat: vi.fn(), conversation: vi.fn(), workflow: vi.fn(), cancel: vi.fn(), analysis: vi.fn() }))
vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, geoguider: { status: m.status, chat: m.chat, conversation: m.conversation, workflow: m.workflow, cancel: m.cancel },
    analyses: { ...actual.api.analyses, get: m.analysis } } }
})
import GeoGuider from './GeoGuider'

const wf = (over: Partial<GgWorkflow> = {}): GgWorkflow => ({ conversation_id: 'c1', state: 'IDLE', pending: null, job_ids: [], jobs: [], cancellable: false, aoi: null, period: null, error: null, ...over })
const msg = (over: Partial<GgMessage>): GgMessage => ({ id: Math.random().toString(36).slice(2), role: 'assistant', content: '', blocks: [], actions: [], created_at: '2026-10-10T10:00:00Z', ...over })
const reply = (assistant: Partial<GgMessage>, workflow = wf(), suggestions: string[] = []): GgChatResponse => ({
  conversation_id: 'c1', messages: [msg({ role: 'user', content: 'x' }), msg(assistant)], workflow, suggestions })

beforeEach(() => {
  vi.clearAllMocks()
  window.sessionStorage.clear()
  useGeoGuider.setState({ open: false, conversationId: null, messages: [], workflow: null, suggestions: [], status: null, busy: false, error: null, lastSent: null })
  useAppStore.setState({ activeAnalysisId: null, drawnBox: null, analyses: [], toasts: [] })
  m.status.mockResolvedValue({ enabled: true, llm: { configured: false, provider: null, mode: 'rules', note: 'No LLM is configured.' }, geocoder: { configured: true },
    satellite: { catalogue: true, imagery: true }, weather: { configured: false }, model: { id: 'oscd-s2-v1', ready: true },
    capabilities: { change_detection: true, weather_alerts: false, results: true } })
})

const open = async () => {
  render(<GeoGuider />)
  await userEvent.click(screen.getByRole('button', { name: 'Open GeoGuider assistant' }))
}

describe('GeoGuider chat', () => {
  it('opens with the welcome message, honest mode banner and only implemented prompts', async () => {
    await open()
    expect(screen.getByText(/I'm GeoGuider, your AI geospatial copilot/)).toBeInTheDocument()
    expect(await screen.findByText(/No LLM is configured/)).toBeInTheDocument()
    expect(screen.getByText('Built-in command parser (no LLM configured)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /changes in Mumbai over the past 10 years/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /weather alerts/ })).not.toBeInTheDocument() // weather is not configured -> prompt hidden
  })

  it('submits with Enter, shows the reply and sends the UI context', async () => {
    useAppStore.setState({ activeAnalysisId: '11111111-1111-4111-8111-111111111111', drawnBox: [1, 2, 3, 4] })
    m.chat.mockResolvedValue(reply({ content: 'Resolved the place to **Mumbai**.' }))
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'Show me changes in Mumbai{Enter}')
    expect(await screen.findByText('Mumbai', { selector: 'strong' })).toBeInTheDocument()
    expect(m.chat).toHaveBeenCalledWith(expect.objectContaining({ message: 'Show me changes in Mumbai', ui: expect.objectContaining({ page: '/dashboard', drawn_bbox: [1, 2, 3, 4], active_analysis_id: '11111111-1111-4111-8111-111111111111' }) }))
    expect(window.sessionStorage.getItem('geoguider_conversation_id')).toBe('c1')
  })

  it('keeps the conversation id for follow-ups and shows suggested follow-up questions', async () => {
    m.chat.mockResolvedValueOnce(reply({ content: 'First' }, wf(), ['What changed the most?'])).mockResolvedValueOnce(reply({ content: 'Second' }))
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'hello{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: 'What changed the most?' }))
    await waitFor(() => expect(m.chat).toHaveBeenCalledTimes(2))
    expect(m.chat.mock.calls[1][0]).toMatchObject({ conversation_id: 'c1', message: 'What changed the most?' })
  })

  it('renders choice cards that are only clickable while they are the current question', async () => {
    const pending = { id: 'p1', kind: 'aoi_size', prompt: 'Choose', options: [{ id: 'c10', label: 'Central 10 × 10 km' }] }
    m.chat.mockResolvedValue(reply({ content: 'Which area?', blocks: [{ type: 'choices', pending_id: 'p1', kind: 'aoi_size', prompt: 'Choose', options: pending.options }] }, wf({ pending })))
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'mumbai{Enter}')
    const btn = await screen.findByRole('button', { name: /Central 10/ })
    expect(btn).toBeEnabled()
    m.chat.mockResolvedValue(reply({ content: 'ok' }))
    await userEvent.click(btn)
    await waitFor(() => expect(m.chat).toHaveBeenLastCalledWith(expect.objectContaining({ choice: { pending_id: 'p1', option_id: 'c10' } })))
    await waitFor(() => expect(screen.getByRole('button', { name: /Central 10/ })).toBeDisabled()) // stale card is inert
  })

  it('shows plan confirmation, then live job progress read from the workflow, with a cancel request', async () => {
    const job = { id: '22222222-2222-4222-8222-222222222222', name: 'Mumbai run', status: 'detecting_changes', progress: 0.4, stage: 'Detecting changes', error: null }
    m.chat.mockResolvedValue(reply({ content: 'Started 1 analysis job(s).', blocks: [{ type: 'progress', analysis_ids: [job.id] }], actions: [{ type: 'track_analyses', analysis_ids: [job.id] }] },
      wf({ state: 'ANALYZING', job_ids: [job.id], jobs: [job], cancellable: true })))
    m.analysis.mockResolvedValue({ id: job.id, name: 'Mumbai run', status: 'detecting_changes' })
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'run it{Enter}')
    expect(await screen.findByText('Detecting changes')).toBeInTheDocument() // the stage text is the backend's, not invented here
    await waitFor(() => expect(m.analysis).toHaveBeenCalledWith(job.id))
    m.cancel.mockResolvedValue(reply({ content: 'Cancellation requested for 1 running job(s).' }, wf({ state: 'ANALYZING', job_ids: [job.id], jobs: [job], cancellable: true })))
    await userEvent.click(screen.getByRole('button', { name: 'Request cancellation' }))
    expect(await screen.findByText(/Cancellation requested/)).toBeInTheDocument()
  })

  it('shows an error with retry that resends the same request', async () => {
    m.chat.mockRejectedValueOnce(Object.assign(new Error('Cannot reach the GeoTrace backend.'), { name: 'ApiError', status: 0 })).mockResolvedValueOnce(reply({ content: 'Back online.' }))
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'hello{Enter}')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Back online.')).toBeInTheDocument()
    expect(m.chat).toHaveBeenCalledTimes(2)
    expect(m.chat.mock.calls[1][0].message).toBe('hello')
  })

  it('executes validated navigation actions and ignores invalid ones', async () => {
    m.chat.mockResolvedValue(reply({ content: 'Opening.', actions: [{ type: 'navigate', route: 'map', panel: 'quick' }, { type: 'navigate', route: 'https://evil.example' }, { type: 'open_analysis', analysis_id: 'not-a-uuid' }] }))
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'open the satellite imagery page{Enter}')
    await waitFor(() => expect(push).toHaveBeenCalledWith('/map'))
    expect(push).toHaveBeenCalledTimes(1)
    expect(m.analysis).not.toHaveBeenCalled()
    expect(useAppStore.getState().leftPanel).toBe('quick')
  })

  it('renders result cards with the five evidence sections and opens the analysis on the map', async () => {
    const id = '33333333-3333-4333-8333-333333333333'
    m.analysis.mockResolvedValue({ id, name: 'Mumbai', status: 'completed', bounds: [72.8, 19, 72.9, 19.1] })
    m.chat.mockResolvedValue(reply({ content: '2 change polygons.', blocks: [{ type: 'result', analysis_id: id, name: 'Mumbai', headline: 'h', model_id: 'oscd-s2-v1', feature_count: 2, changed_area_m2: 80000,
      sections: { observed: ['Imagery A'], computed: ['2 polygons'], predictions: ['Model output'], interpretation: ['Candidate differences'], limitations: ['Seasonal effects'] } }] }))
    await open()
    await userEvent.type(screen.getByLabelText('Message GeoGuider'), 'explain my latest analysis{Enter}')
    for (const t of ['Observed input data', 'Computed metrics', 'Model predictions', 'Interpretation (hypotheses)', 'Limitations']) expect(await screen.findByText(t)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Show on map/ }))
    await waitFor(() => expect(useAppStore.getState().activeAnalysisId).toBe(id))
  })

  it('is keyboard accessible: dialog role, labelled input, Escape closes', async () => {
    await open()
    const dialog = screen.getByRole('dialog', { name: 'GeoGuider assistant' })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByLabelText('Message GeoGuider')).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open GeoGuider assistant' })).toBeInTheDocument()
  })

  it('restores the previous conversation after a reload', async () => {
    window.sessionStorage.setItem('geoguider_conversation_id', 'c1')
    m.conversation.mockResolvedValue({ id: 'c1', title: 't', updated_at: '2026-10-10T10:00:00Z', messages: [msg({ role: 'user', content: 'earlier question' }), msg({ content: 'earlier answer' })], workflow: wf() })
    await open()
    expect(await screen.findByText('earlier question')).toBeInTheDocument()
    expect(screen.getByText('earlier answer')).toBeInTheDocument()
  })

  it('polls the real workflow while a job runs and posts the announced results', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const job = { id: '44444444-4444-4444-8444-444444444444', name: 'r', status: 'queued', progress: 0, stage: null, error: null }
    useGeoGuider.setState({ conversationId: 'c1', workflow: wf({ state: 'PREPROCESSING', job_ids: [job.id], jobs: [job], cancellable: true }) })
    m.workflow.mockResolvedValue({ workflow: wf({ state: 'COMPLETED', job_ids: [job.id] }), new_messages: [msg({ content: 'Results are ready.' })] })
    await open()
    await act(async () => { await vi.advanceTimersByTimeAsync(4100) })
    expect(await screen.findByText('Results are ready.')).toBeInTheDocument()
    vi.useRealTimers()
  })
})
