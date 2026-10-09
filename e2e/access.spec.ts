import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/**
 * Browser tests with the API stubbed at the network layer. They verify authorization gating, truthful error
 * states and empty states. The full upload -> detect -> export workflow runs against a real backend in
 * acceptance.spec.ts.
 */
type Role = 'admin' | 'user' | 'viewer'

const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })

async function stubApi(page: Page, role: Role | null, opts: { systemDown?: boolean; meDelayMs?: number } = {}) {
  if (role) await page.addInitScript(() => window.localStorage.setItem('terratrack_access_token', 'e2e-token'))
  await page.route('**/api/v1/auth/me', async (r) => {
    if (opts.meDelayMs) await new Promise((res) => setTimeout(res, opts.meDelayMs))
    if (!role) return r.fulfill(json({ detail: 'Not authenticated' }, 401))
    return r.fulfill(json({ id: `e2e-${role}`, email: `${role}@example.test`, name: `E2E ${role}`, role, is_active: true, created_at: '2026-01-01T00:00:00Z' }))
  })
  await page.route('**/api/v1/system/status', (r) => (opts.systemDown
    ? r.abort('connectionrefused')
    : r.fulfill(json({ version: 'test', env: 'test', demo_mode: false, database: { ok: true, error: null }, storage: { ok: true }, job_runner: 'embedded', job_concurrency: 1,
      ml: { code_available: false, torch: false, cuda: false, device: null, default_model: null, models: [], any_model_ready: false }, sentinel: [], llm: { configured: false, provider: 'none' },
      limits: { max_upload_mb: 500, max_raster_pixels: 100000000, max_aoi_km2: 2500 } }))))
  await page.route('**/api/v1/projects**', (r) => r.fulfill(json([{ id: 'p1', name: 'My workspace', description: null, owner_id: 'u', visibility: 'private', is_demo: false, created_at: '', updated_at: '', analysis_count: 0, can_write: true }])))
  await page.route('**/api/v1/analyses**', (r) => r.fulfill(json([])))
  await page.route('**/api/v1/layers**', (r) => r.fulfill(json([])))
  await page.route('**/api/v1/regions/**', (r) => r.fulfill(json({ regions: [], total: 0 })))
  await page.route('**/api/v1/alerts/stats', (r) => r.fulfill(json({ by_status: {}, unresolved_by_severity: {}, unresolved: 0 })))
  await page.route('**/api/v1/alerts**', (r) => r.fulfill(json({ total: 0, open: 0, limit: 25, offset: 0, items: [] })))
  await page.route('**/api/v1/analytics/overview**', (r) => r.fulfill(json({ analyses: { total: 0, completed: 0, running: 0, failed: 0 }, analyzed_area_m2: 0, changed_area_m2: 0, feature_count: 0, by_severity: {}, by_category: {}, series: [], has_demo: false })))
  await page.route('**/api/v1/users/**', (r) => r.fulfill(json([])))
}

test('unauthenticated visitors see the sign-in form and no protected content', async ({ page }) => {
  await stubApi(page, null)
  await page.goto('/dashboard')
  await expect(page.getByRole('form', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Overview' })).toHaveCount(0)
})

for (const role of ['admin', 'user', 'viewer'] as const) {
  test(`${role} reaches the overview, which shows an honest empty state`, async ({ page }) => {
    await stubApi(page, role)
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
    await expect(page.getByText('No completed analyses yet')).toBeVisible()
    await expect(page.getByText(/demo data/i)).toHaveCount(0)
  })
}

test.describe('administration is admin-only', () => {
  test('admin sees user management', async ({ page }) => {
    await stubApi(page, 'admin')
    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible()
  })
  for (const role of ['user', 'viewer'] as const) {
    test(`${role} is denied`, async ({ page }) => {
      await stubApi(page, role)
      await page.goto('/admin/users')
      await expect(page.getByRole('heading', { name: 'Access denied' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'User Management' })).toHaveCount(0)
    })
  }
})

test('viewers cannot start analyses or create alert rules', async ({ page }) => {
  await stubApi(page, 'viewer')
  await page.goto('/analyses')
  await expect(page.getByRole('link', { name: /New analysis/ })).toHaveCount(0)
  await page.goto('/alerts')
  await expect(page.getByRole('heading', { name: 'Alert centre' })).toBeVisible()
  await expect(page.getByRole('button', { name: /New rule/ })).toHaveCount(0)
})

test('an unreachable backend is reported, never replaced by sample data', async ({ page }) => {
  await stubApi(page, 'user', { systemDown: true })
  await page.goto('/dashboard')
  await expect(page.getByText('Backend unavailable')).toBeVisible()
  await expect(page.getByText(/Nothing shown below is substituted with sample data/)).toBeVisible()
})

test('protected content is not shown while the session is being verified', async ({ page }) => {
  await stubApi(page, 'viewer', { meDelayMs: 600 })
  await page.goto('/admin/users')
  await expect(page.getByRole('heading', { name: 'User Management' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Access denied' })).toBeVisible()
})

test('every sidebar destination renders a page (no dead links)', async ({ page }) => {
  await stubApi(page, 'user')
  for (const [path, heading] of [['/dashboard', 'Overview'], ['/analyses', 'Analyses'], ['/regions', 'Monitored regions'], ['/changes', 'Change intelligence'], ['/alerts', 'Alert centre'],
    ['/analytics', 'Analytics'], ['/reports', 'Reports & exports'], ['/settings', 'Settings & system status']] as const) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading, exact: true }), path).toBeVisible()
  }
})
