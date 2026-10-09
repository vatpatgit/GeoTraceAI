import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

/**
 * End-to-end acceptance workflow against a REAL backend (no network stubs):
 * sign in -> upload before/after GeoTIFFs -> automatic slider comparison -> ML changes -> save as analysis -> polygons appear and are selectable
 * -> export GeoJSON that is valid and matches the stored count -> an alert rule created beforehand yields incidents for the new detections -> a PDF report downloads.
 *
 * Prerequisites (see README "Acceptance test"): backend running with CORS allowing this origin, a user, and the synthetic
 * fixtures (python backend/scripts/make_e2e_fixtures.py <dir>). Configure with:
 *   E2E_EMAIL, E2E_PASSWORD, E2E_FIXTURE_DIR, optional E2E_API_BASE (default http://localhost:8000/api/v1)
 * The test is skipped (not passed) when these are missing or the backend is unreachable.
 */
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const FIXTURES = process.env.E2E_FIXTURE_DIR
const API = process.env.E2E_API_BASE || 'http://localhost:8000/api/v1'

test.describe.configure({ mode: 'serial' })

test('upload -> detect -> explore -> export -> alert -> report', async ({ page, request }, testInfo) => {
  test.skip(!EMAIL || !PASSWORD || !FIXTURES, 'E2E_EMAIL, E2E_PASSWORD and E2E_FIXTURE_DIR are required')
  const before = path.join(FIXTURES!, 'scene_before.tif')
  const after = path.join(FIXTURES!, 'scene_after.tif')
  test.skip(!fs.existsSync(before) || !fs.existsSync(after), `fixtures not found in ${FIXTURES}`)
  const health = await request.get(API.replace(/\/api\/v1$/, '') + '/health').catch(() => null)
  test.skip(!health || !health.ok(), `backend not reachable at ${API}`)
  test.setTimeout(240_000)

  // ---- sign in through the UI
  await page.goto('/analyses/new')
  await page.getByLabel('Email').fill(EMAIL!)
  await page.getByLabel('Password').fill(PASSWORD!)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'New analysis' })).toBeVisible()

  // ---- an alert rule exists before the analysis runs (rules are evaluated when a job completes)
  const ruleName = `E2E rule ${Date.now()}`
  await page.goto('/alerts')
  await page.getByRole('button', { name: /New rule/ }).click()
  await page.getByLabel('Name').fill(ruleName)
  await page.getByRole('button', { name: 'Create rule' }).click()
  await expect(page.getByText('Rule created')).toBeVisible()
  await page.goto('/analyses/new')

  // ---- upload both scenes; the server validates content and reports georeferencing
  await page.getByLabel('1. Before image GeoTIFF file').setInputFiles(before)
  await page.getByLabel('2. After image GeoTIFF file').setInputFiles(after)
  await expect(page.getByText('scene_before.tif')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('scene_after.tif')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('EPSG:32633').first()).toBeVisible()
  await expect(page.getByText('Pair is compatible')).toBeVisible({ timeout: 60_000 })

  // ---- no button press: as soon as the pair validates, the slider comparison opens on the map
  await expect(page).toHaveURL(/\/map/, { timeout: 90_000 })
  await expect(page.getByRole('slider', { name: 'Before and after comparison position' })).toBeVisible({ timeout: 90_000 })

  // ---- ML change detection on the two uploaded images, then store it as a normal analysis
  await page.getByRole('switch', { name: 'Show changes detected by the ML model' }).click()
  await expect(page.getByText(/areas? flagged/)).toBeVisible({ timeout: 180_000 })
  const name = `E2E ${Date.now()}`
  await page.getByRole('button', { name: /Save as analysis/ }).click()
  const rows = page.getByRole('listbox').getByRole('option')
  await expect(rows.first()).toBeVisible({ timeout: 240_000 })
  const count = await rows.count()
  expect(count).toBeGreaterThan(0)

  // ---- selecting a detection updates the intelligence panel (shared selection)
  await rows.first().click()
  await expect(page.getByText(/Observed|observed/).first()).toBeVisible()

  // ---- export: GeoJSON is valid and matches the stored count
  await page.getByRole('tab', { name: /Downloads/ }).click()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('div.hairline-b', { hasText: 'All features' }).getByRole('button', { name: /GeoJSON/ }).click(),
  ])
  const file = testInfo.outputPath('export.geojson')
  await download.saveAs(file)
  const fc = JSON.parse(fs.readFileSync(file, 'utf8'))
  expect(fc.type).toBe('FeatureCollection')
  expect(fc.metadata.scope).not.toBe('selected')
  expect(fc.features.length).toBe(fc.metadata.feature_count)
  expect(fc.features.length).toBeGreaterThanOrEqual(count)
  for (const f of fc.features) {
    expect(['Polygon', 'MultiPolygon']).toContain(f.geometry.type)
    expect(f.properties.area_m2).toBeGreaterThan(0)
  }

  // ---- the rule fired for the detections, with stored evidence
  await page.goto('/alerts')
  await expect(page.getByText(`Rule “${ruleName}”`).first()).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Show evidence' }).first().click()
  await expect(page.getByText(/Why this alert fired/)).toBeVisible()

  // ---- a PDF report is generated from the stored record
  await page.goto('/reports')
  const row = page.getByRole('listitem').filter({ hasText: /ML change: scene_before/ }).first()
  const [report] = await Promise.all([page.waitForEvent('download'), row.getByRole('button', { name: /PDF/ }).click()])
  const pdf = testInfo.outputPath('report.pdf')
  await report.saveAs(pdf)
  expect(fs.readFileSync(pdf).subarray(0, 5).toString()).toBe('%PDF-')
})
