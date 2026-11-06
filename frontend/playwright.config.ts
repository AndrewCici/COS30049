import { defineConfig, devices } from '@playwright/test';

// e2e/ exercises the real app against the real backend (see webServer
// below) rather than a mocked API, except where a test specifically needs
// to simulate the backend being unreachable (backend-down.spec.ts), which
// intercepts requests at the network layer instead of stopping the server
// out from under the other tests sharing it.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: '../.venv/bin/uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/api/v1/health',
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
