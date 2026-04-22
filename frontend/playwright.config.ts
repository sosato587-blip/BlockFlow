import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for BlockFlow E2E tests.
 *
 * Runs against the STAGING stack (3100/8100) with `BLOCKFLOW_MOCK_RUNPOD=1`
 * so tests never hit RunPod — zero GPU cost, deterministic results.
 *
 * Assumes staging is already running. Spin it up with:
 *   $env:BLOCKFLOW_MOCK_RUNPOD="1"; $env:BACKEND_PORT="8100"; $env:FRONTEND_PORT="3100"; uv run app.py
 *
 * First-time browser install (~500MB, one-time):
 *   npx playwright install chromium
 *
 * Run tests:
 *   npx playwright test
 */

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false, // some tests share sessionStorage state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
