import { describe, expect, it } from 'vitest'
import type { WeatherAlert } from '@/lib/api'
import { alertWindow, geometryBBox, WEATHER_COLOR, WEATHER_RANK, weatherFeatureCollection } from './weather'

const poly = { type: 'Polygon' as const, coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] }
const alert = (over: Partial<WeatherAlert> = {}): WeatherAlert => ({
  id: 'a1', aoi_id: 'x', aoi_name: 'AOI', provider: 'openweather', source_alert_id: 'S1', source: 'government', title: 'Flood', description: null, tags: ['flood'],
  severity: 'severe', urgency: 'expected', certainty: 'likely', industry: [], geometry: poly, start_time: '2026-10-10T12:00:00Z', end_time: '2026-10-10T15:00:00Z',
  status: 'active', change_count: 0, first_seen_at: '', last_seen_at: '', last_checked_at: '', notified_at: null, ...over,
})

describe('weather helpers', () => {
  it('severity colours are distinct and ranked', () => {
    expect(new Set(Object.values(WEATHER_COLOR)).size).toBe(5)
    expect(WEATHER_RANK.extreme).toBeGreaterThan(WEATHER_RANK.severe)
    expect(WEATHER_RANK.unknown).toBe(0)
  })
  it('map features include only active alerts that carry geometry, styled by severity and selection', () => {
    const fc = weatherFeatureCollection([alert(), alert({ id: 'a2', geometry: null }), alert({ id: 'a3', status: 'expired' }), alert({ id: 'a4', severity: 'extreme' })], 'a4')
    expect(fc.features.map((f) => f.id)).toEqual(['a1', 'a4'])
    expect(fc.features[1].properties).toMatchObject({ severity: 'extreme', color: WEATHER_COLOR.extreme, selected: 1 })
    expect(fc.features[0].properties.selected).toBe(0)
  })
  it('computes a bounding box for polygons and points and null for nothing', () => {
    expect(geometryBBox(poly)).toEqual([10, 50, 11, 51])
    expect(geometryBBox({ type: 'Point', coordinates: [5, 6] })).toEqual([5, 6, 5, 6])
    expect(geometryBBox(null)).toBeNull()
  })
  it('never invents event times', () => {
    expect(alertWindow({ start_time: null, end_time: null })).toBe('Time not provided')
    expect(alertWindow(alert())).toContain('→')
  })
})
