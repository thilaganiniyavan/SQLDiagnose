import { defineConfig, devices } from '@playwright/test'

// End-to-end tests against the real API serving the built app:
//   make frontend && make api      (or let `webServer` start the API)
//   npm run e2e
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: '../.venv/bin/python -m uvicorn deployment.api.main:app --port 8000',
        cwd: '..',
        url: `${baseURL}/api/v1/health`,
        reuseExistingServer: true,
        timeout: 180_000,
      },
})
