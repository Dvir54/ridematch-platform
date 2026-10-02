import { defineConfig, devices } from '@playwright/test'
import { resolve } from 'node:path'
import { REDIS_URL, TEST_DATABASE_URL } from './env'

const root = resolve(import.meta.dirname, '../..')
const FRONTEND = 'http://localhost:5173'
const API = 'http://127.0.0.1:8000'

/**
 * Full stack: real backend (APP_ENV=test → the throwaway ridematch_test DB, which
 * pytest builds from contracts/schema.sql), real Vite dev server, real Clerk dev
 * instance. Only Mapbox is stubbed, in the spec, so runs don't depend on it.
 */
export default defineConfig({
  testDir: './specs',
  globalSetup: './support/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: FRONTEND,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'uv run uvicorn app.main:app --port 8000',
      cwd: resolve(root, 'backend'),
      url: `${API}/api/v1/health`,
      reuseExistingServer: true,
      stdout: 'ignore',
      stderr: 'pipe',
      timeout: 60_000,
      env: {
        APP_ENV: 'test',
        TEST_DATABASE_URL,
        REDIS_URL,
        JOBS_ENABLED: 'false',
        EMAIL_BACKEND: 'memory',
        CLERK_AUTHORIZED_PARTIES: FRONTEND,
        CORS_ORIGINS: FRONTEND,
      },
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      cwd: resolve(root, 'frontend'),
      url: FRONTEND,
      reuseExistingServer: true,
      stdout: 'ignore',
      stderr: 'pipe',
      timeout: 60_000,
      env: {
        VITE_API_BASE_URL: `${API}/api/v1`,
        VITE_WS_URL: 'ws://127.0.0.1:8000/api/v1/ws',
        // Any non-empty token switches address suggestions on; the spec answers the request.
        VITE_MAPBOX_TOKEN: 'pk.e2e',
      },
    },
  ],
})
