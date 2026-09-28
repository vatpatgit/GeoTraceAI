import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

type Role = 'Admin' | 'Researcher' | 'Viewer'

async function mockSession(page: Page, role: Role, delay = 0) {
    await page.addInitScript(() => {
        window.localStorage.setItem('terratrack_access_token', 'browser-test-token')
    })
    await page.route('**/api/v1/auth/me', async (route) => {
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay))
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                id: `browser-${role.toLowerCase()}`,
                email: `${role.toLowerCase()}@example.test`,
                name: role,
                role: role.toLowerCase() === 'admin' ? 'admin' : role.toLowerCase() === 'researcher' ? 'researcher' : 'viewer',
                created_at: '2026-01-01T00:00:00Z',
            }),
        })
    })
}

async function mockUsersApi(page: Page) {
    let users = [{ id: 'user-1', name: 'Ada Lovelace', email: 'ada@example.test', role: 'user', is_active: true, created_at: '2026-01-01T00:00:00Z' }]
    await page.route('**/api/v1/users/**', async (route) => {
        const request = route.request()
        const url = new URL(request.url())
        const userId = url.pathname.match(/\/users\/([^/]+)/)?.[1]
        if (request.method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(users) })
        if (request.method() === 'POST') {
            const input = request.postDataJSON()
            const created = { id: `user-${users.length + 1}`, name: input.name, email: input.email, role: input.role, is_active: true, created_at: '2026-01-02T00:00:00Z' }
            users.push(created)
            return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) })
        }
        const user = users.find((item) => item.id === userId)
        if (!user) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'User not found' }) })
        if (request.method() === 'PATCH') {
            const input = request.postDataJSON()
            if (url.pathname.endsWith('/role')) user.role = input.role
            else if (url.pathname.endsWith('/status')) user.is_active = input.is_active
            else Object.assign(user, input)
            return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(user) })
        }
        if (request.method() === 'DELETE') {
            users = users.filter((item) => item.id !== userId)
            return route.fulfill({ status: 204, body: '' })
        }
        return route.continue()
    })
}

async function mockUsersResponse(page: Page, status: number, body: unknown, delay = 0) {
    await page.route('**/api/v1/users/**', async (route) => {
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay))
        await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    })
}

async function mockDashboardDataApis(page: Page) {
    await page.route('**/api/v1/regions/**', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                regions: [{
                    id: '00000000-0000-0000-0000-000000000001',
                    name: 'Amazon Basin',
                    center_lat: 0,
                    center_lng: -64,
                    area_km2: 7000000,
                    risk_level: 'critical',
                    geometry: {
                        type: 'Polygon',
                        coordinates: [[[-70.5, -3.5], [-59.0, 0.5], [-65.0, 5.0], [-70.5, -3.5]]],
                    },
                }],
                total: 1,
            }),
        })
    })

    await page.route('**/api/v1/alerts/**', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ alerts: [], total: 0, unread: 0 }),
        })
    })

    await page.route('**/api/v1/analytics/**', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ total_events: 0, total_area_affected_km2: 0, avg_confidence: 0, by_type: {}, recent_events: [] }),
        })
    })
}

test('dashboard requests Sentinel imagery for the selected region and date', async ({ page }) => {
    await mockSession(page, 'Viewer')
    await mockDashboardDataApis(page)

    let imageryRequested = false
    await page.route('**/api/v1/sentinel/imagery', async (route) => {
        imageryRequested = true
        const body = route.request().postDataJSON() as { region_id?: string; date?: string }
        expect(body.region_id).toBe('00000000-0000-0000-0000-000000000001')
        expect(body.date).toBeTruthy()
        const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
        await route.fulfill({ status: 200, contentType: 'image/png', body: png })
    })

    await page.goto('/dashboard')
    await expect(page.locator('#dashboard-root')).toBeVisible()
    await expect.poll(() => imageryRequested, { timeout: 15000 }).toBe(true)
    await expect(page.getByText(/Sentinel-2 •/)).toBeVisible({ timeout: 15000 })
})

test('dashboard shows fallback when Sentinel imagery fails', async ({ page }) => {
    await mockSession(page, 'Viewer')
    await mockDashboardDataApis(page)

    await page.route('**/api/v1/sentinel/imagery', async (route) => {
        await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Sentinel Hub error' }),
        })
    })

    await page.goto('/dashboard')
    await expect(page.locator('#dashboard-root')).toBeVisible()
    await expect(page.getByText('Sentinel-2 unavailable • Using base imagery')).toBeVisible({ timeout: 15000 })
})

test('unauthenticated dashboard shows the login flow', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: 'Sign in to TerraTrack' })).toBeVisible()
    await expect(page.locator('#dashboard-root')).toHaveCount(0)
})

test.describe('authenticated dashboard access', () => {
    for (const role of ['Admin', 'Researcher', 'Viewer'] as const) {
        test(`${role} can access the dashboard`, async ({ page }) => {
            await mockSession(page, role)
            await page.goto('/dashboard')
            await expect(page.locator('#dashboard-root')).toBeVisible()
            await expect(page.getByText(role, { exact: true })).toBeVisible()
        })
    }
})

test.describe('admin route authorization', () => {
    test('admin can access user management directly', async ({ page }) => {
        await mockSession(page, 'Admin')
        await page.goto('/admin/users')
        await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible()
        await expect(page.getByText('Access Denied')).toHaveCount(0)
    })

    for (const role of ['Researcher', 'Viewer'] as const) {
        test(`${role} sees Access Denied on direct admin navigation`, async ({ page }) => {
            await mockSession(page, role)
            await page.goto('/admin/users')
            await expect(page.getByRole('heading', { name: 'Access Denied' })).toBeVisible()
            await expect(page.getByRole('link', { name: 'Return to Dashboard' })).toBeVisible()
        })
    }
})

test('hydration does not expose protected content before authorization', async ({ page }) => {
    await mockSession(page, 'Viewer', 500)
    await page.goto('/admin/users')
    await expect(page.getByText('Checking your session...')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'User Management' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Access Denied' })).toBeVisible()
})

test('admin can load, create, edit, toggle, and delete users', async ({ page }) => {
    await mockSession(page, 'Admin')
    await mockUsersApi(page)
    await page.goto('/admin/users')
    await expect(page.getByText('Ada Lovelace')).toBeVisible()

    await page.getByRole('button', { name: 'Create User' }).click()
    await page.getByLabel('Name').fill('Grace Hopper')
    await page.getByLabel('Email').fill('grace@example.test')
    await page.getByLabel('Password').fill('a-secure-password')
    await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
    await expect(page.getByText('Grace Hopper')).toBeVisible()

    const graceRow = page.getByRole('row').filter({ hasText: 'Grace Hopper' })
    await graceRow.getByRole('button', { name: 'Edit' }).click()
    await page.getByRole('dialog').getByLabel('Role').selectOption('admin')
    await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
    await expect(graceRow.getByText('ADMIN')).toBeVisible()

    await page.once('dialog', (dialog) => dialog.accept())
    await graceRow.getByRole('button', { name: 'Deactivate' }).click()
    await expect(graceRow.getByText('Inactive')).toBeVisible()
    await graceRow.getByRole('button', { name: 'Activate' }).click()
    await expect(graceRow.getByText('Active')).toBeVisible()
    await page.once('dialog', (dialog) => dialog.accept())
    await graceRow.getByRole('button', { name: 'Delete Grace Hopper' }).click()
    await expect(page.getByText('Grace Hopper')).toHaveCount(0)
})

test('admin user page shows loading and empty states', async ({ page }) => {
    await mockSession(page, 'Admin')
    await mockUsersResponse(page, 200, [], 500)
    await page.goto('/admin/users')
    await expect(page.getByText('Loading users...')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'No users found' })).toBeVisible()
})

test('admin user page shows backend errors without fake users', async ({ page }) => {
    await mockSession(page, 'Admin')
    await mockUsersResponse(page, 500, { detail: 'Database unavailable' })
    await page.goto('/admin/users')
    await expect(page.getByText('Unable to load users. Please try again.')).toBeVisible()
    await expect(page.getByText('Ada Lovelace')).toHaveCount(0)
})
