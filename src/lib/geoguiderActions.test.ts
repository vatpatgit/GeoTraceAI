import { describe, expect, it } from 'vitest'
import type { GgAction } from '@/lib/api/geoguider'
import { isValidAction } from './geoguiderActions'

const ID = '55555555-5555-4555-8555-555555555555'

describe('GeoGuider action allow-list', () => {
  it.each<[GgAction, boolean]>([
    [{ type: 'navigate', route: 'map', panel: 'quick' }, true],
    [{ type: 'navigate', route: 'settings' }, true],
    [{ type: 'navigate', route: 'https://evil.example' }, false],
    [{ type: 'navigate', route: '../admin' }, false],
    [{ type: 'navigate', route: 'map', panel: '<img onerror=x>' }, false],
    [{ type: 'show_aoi', bbox: [72.8, 19, 72.9, 19.1], aoi_id: ID, name: 'x' }, true],
    [{ type: 'show_aoi', bbox: [72.9, 19, 72.8, 19.1], aoi_id: ID, name: 'x' }, false],
    [{ type: 'show_aoi', bbox: [0, 0, 999, 1], aoi_id: ID, name: 'x' }, false],
    [{ type: 'show_aoi', bbox: [NaN, 0, 1, 1], aoi_id: ID, name: 'x' }, false],
    [{ type: 'open_analysis', analysis_id: ID }, true],
    [{ type: 'open_analysis', analysis_id: '../../etc/passwd' }, false],
    [{ type: 'track_analyses', analysis_ids: [ID] }, true],
    [{ type: 'track_analyses', analysis_ids: [] }, false],
    [{ type: 'zoom_to', center: [72.8, 19.1] }, true],
    [{ type: 'zoom_to', center: [500, 19.1] }, false],
    [{ type: 'download_export', path: `/analyses/${ID}/export?format=geojson`, format: 'geojson', name: 'n' }, true],
    [{ type: 'download_export', path: `/reports/analyses/${ID}?format=pdf`, format: 'pdf', name: 'n' }, true],
    [{ type: 'download_export', path: 'https://evil.example/x', format: 'geojson', name: 'n' }, false],
    [{ type: 'download_export', path: `/users/${ID}`, format: 'geojson', name: 'n' }, false],
    [{ type: 'show_weather' }, true],
    [{ type: 'start_draw' }, true],
    [{ type: 'run_js' } as unknown as GgAction, false],
  ])('%j -> %s', (action, ok) => {
    expect(isValidAction(action)).toBe(ok)
  })
})
