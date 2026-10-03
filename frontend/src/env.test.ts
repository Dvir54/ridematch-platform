import { describe, expect, it } from 'vitest'
import { readEnv } from './env'

describe('readEnv', () => {
  it('falls back to the local backend in development', () => {
    const env = readEnv({ PROD: false, DEV: true, MODE: 'development' })
    expect(env.apiBaseUrl).toBe('http://localhost:8000/api/v1')
    expect(env.wsUrl).toBe('ws://localhost:8000/api/v1/ws')
    expect(env.missing).toEqual([])
  })

  it('never falls back to localhost in a production build', () => {
    const env = readEnv({ PROD: true, MODE: 'production' })
    expect(env.apiBaseUrl).toBe('')
    expect(env.wsUrl).toBe('')
    expect(env.missing).toEqual(['VITE_API_BASE_URL', 'VITE_WS_URL'])
  })

  it('accepts a complete production configuration', () => {
    const env = readEnv({
      PROD: true,
      MODE: 'production',
      VITE_API_BASE_URL: 'https://api.ridematch.app/api/v1',
      VITE_WS_URL: 'wss://api.ridematch.app/api/v1/ws',
      VITE_SENTRY_DSN: 'https://key@sentry.example/1',
    })
    expect(env.missing).toEqual([])
    expect(env.apiBaseUrl).toBe('https://api.ridematch.app/api/v1')
    expect(env.sentryDsn).toBe('https://key@sentry.example/1')
  })
})
