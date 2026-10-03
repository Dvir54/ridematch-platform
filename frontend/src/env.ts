/**
 * Every browser-visible setting, read once. Vite's `envDir: '..'` points at the
 * repo root, so these come from the same shared .env the backend uses.
 *
 * In development a missing API or WebSocket URL falls back to the local backend.
 * A production bundle has no such fallback: a missing URL is listed in
 * `missing`, and the app shows the configuration screen instead of quietly
 * calling localhost from a user's browser.
 */
type Source = Partial<Record<string, string | boolean | undefined>>

export interface Env {
  apiBaseUrl: string
  wsUrl: string
  clerkPublishableKey: string
  mapboxToken: string
  sentryDsn: string
  useMocks: boolean
  /** Required `VITE_*` variables a production build was built without. */
  missing: string[]
}

const DEV_API = 'http://localhost:8000/api/v1'
const DEV_WS = 'ws://localhost:8000/api/v1/ws'

function text(source: Source, key: string): string {
  const value = source[key]
  return typeof value === 'string' ? value.trim() : ''
}

export function readEnv(source: Source): Env {
  const production = source.PROD === true
  const apiBaseUrl = text(source, 'VITE_API_BASE_URL')
  const wsUrl = text(source, 'VITE_WS_URL')
  const missing: string[] = []
  if (production && !apiBaseUrl) missing.push('VITE_API_BASE_URL')
  if (production && !wsUrl) missing.push('VITE_WS_URL')

  return {
    apiBaseUrl: apiBaseUrl || (production ? '' : DEV_API),
    wsUrl: wsUrl || (production ? '' : DEV_WS),
    clerkPublishableKey: text(source, 'VITE_CLERK_PUBLISHABLE_KEY'),
    mapboxToken: text(source, 'VITE_MAPBOX_TOKEN'),
    sentryDsn: text(source, 'VITE_SENTRY_DSN'),
    useMocks: source.VITE_USE_MOCKS === 'true' || source.MODE === 'mock',
    missing,
  }
}

export const env: Env = readEnv(import.meta.env)
