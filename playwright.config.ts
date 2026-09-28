import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
    testDir: './e2e',
    fullyParallel: true,
    reporter: 'list',
    use: {
        baseURL: 'http://127.0.0.1:3100',
        trace: 'retain-on-failure',
    },
    webServer: {
        command: 'npm run dev -- -p 3100',
        url: 'http://127.0.0.1:3100',
        reuseExistingServer: false,
        timeout: 120_000,
    },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
})
