import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fetchRegions } from './mockApi'
import { listAlerts } from './alertsApi'

describe('backend data clients', () => {
    beforeEach(() => {
        vi.restoreAllMocks()
        vi.stubGlobal('fetch', vi.fn())
        Object.defineProperty(globalThis, 'localStorage', { value: { getItem: () => 'test-token' }, configurable: true })
    })

    it('normalizes backend region IDs and geometry without remapping them', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ regions: [{ id: 'backend-region-9', name: 'North', center_lat: 1, center_lng: 2, area_km2: 42, risk_level: 'high', geometry: { type: 'Polygon', coordinates: [[[1, 2], [3, 4], [1, 2]]] } }], total: 1 }), { status: 200 }))
        const regions = await fetchRegions()
        expect(regions[0].id).toBe('backend-region-9')
        expect(regions[0].geometry?.type).toBe('Polygon')
    })

    it('returns backend alerts and preserves server errors', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ alerts: [{ id: 'alert-1', alert_config_id: 'config-1', change_event_id: 'event-1', severity: 'critical', message: 'Change detected', is_read: false, created_at: '2026-08-26T00:00:00Z' }], total: 1, unread: 1 }), { status: 200 }))
        expect((await listAlerts()).alerts[0].id).toBe('alert-1')

        vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Forbidden' }), { status: 403 }))
        await expect(listAlerts()).rejects.toMatchObject({ status: 403 })
    })
})