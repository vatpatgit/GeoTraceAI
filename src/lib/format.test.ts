import { describe, expect, it } from 'vitest'
import { categoryLabel, formatArea, formatBytes, formatCoord, formatDate, formatM2, formatPct, formatRelative, toTitle } from './format'

describe('formatArea', () => {
  it('uses m2 / ha / km2 with correct unit conversion', () => {
    expect(formatArea(480_000)).toBe('48 ha')
    expect(formatArea(999)).toBe('999 m²')
    expect(formatArea(2_500_000)).toBe('2.5 km²')
    expect(formatArea(10_000)).toBe('1 ha')
  })
  it('handles missing values without printing NaN', () => {
    expect(formatArea(null)).toBe('-')
    expect(formatArea(NaN)).toBe('-')
    expect(formatM2(undefined)).toBe('-')
  })
})

describe('formatters', () => {
  it('formats percentages, dates, bytes, coordinates', () => {
    expect(formatPct(0.1234)).toBe('12.3%')
    expect(formatPct(null)).toBe('-')
    expect(formatDate('2024-06-20T10:30:00Z')).toBe('2024-06-20')
    expect(formatDate('2024-06-20T10:30:00Z', { time: true })).toBe('2024-06-20 10:30Z')
    expect(formatDate('garbage')).toBe('-')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(3 * 1024 ** 3)).toBe('3.00 GB')
    expect(formatCoord(15.0123, 40.6234, 3)).toBe('40.623°N 15.012°E')
    expect(formatCoord(-70.5, -3.25, 2)).toBe('3.25°S 70.50°W')
  })
  it('formats relative time', () => {
    const now = Date.parse('2024-06-20T12:00:00Z')
    expect(formatRelative('2024-06-20T11:59:50Z', now)).toBe('just now')
    expect(formatRelative('2024-06-20T11:30:00Z', now)).toBe('30 min ago')
    expect(formatRelative('2024-06-20T09:00:00Z', now)).toBe('3 h ago')
  })
  it('labels categories with an honest vocabulary', () => {
    expect(categoryLabel('unclassified_change')).toBe('Unclassified change')
    expect(categoryLabel('something_new')).toBe('Something New')
    expect(toTitle('a_b')).toBe('A B')
  })
})
