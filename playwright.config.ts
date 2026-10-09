import { defineConfig, devices } from '@playwright/test'

// By default the suite starts its own dev server on :3100 (the mocked-API specs need nothing else).
// Set E2E_BASE_URL to run against an already running frontend (e.g. http://localhost:3000) -
// required for acceptance.spec.ts, whose backend must allow that origin via CORS_ORIGINS.
const external = process.env.E2E_BASE_URL

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: external || 'http://127.0.0.1:3100',
    trace: 'retain-on-failure',
  },
  ...(external
    ? {}
    : {
        webServer: {
          command: 'npm run dev -- -p 3100',
          url: 'http://127.0.0.1:3100',
          reuseExistingServer: true,
          timeout: 120_000,
        },
      }),
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
