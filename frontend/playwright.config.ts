import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:4173' },
  webServer: [
    {
      command: 'cd .. && uv run --locked uvicorn tests.browser_server:app --host 127.0.0.1 --port 8000 --no-access-log',
      url: 'http://127.0.0.1:8000/health/live',
      env: { EVENTFLOW_ENVIRONMENT: 'test' },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --port 4173',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
