import * as Sentry from '@sentry/react'
import { afterEach, describe, expect, it } from 'vitest'
import { initMonitoring, redact, stripQuery } from './monitoring'

const EMAIL = 'secret.person@ridematch.test'
const JWT = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.c2lnbmF0dXJl'
const LOCATION = 'from_lat=32.0743'

/** Starts a real client whose transport keeps every serialised envelope in memory. */
function captureEnvelopes(): string[] {
  const sent: string[] = []
  const decoder = new TextDecoder()
  initMonitoring('https://public@sentry.example.invalid/1', {
    transport: (options) =>
      Sentry.createTransport(options, async (request) => {
        sent.push(typeof request.body === 'string' ? request.body : decoder.decode(request.body))
        return { statusCode: 200 }
      }),
  })
  return sent
}

afterEach(async () => {
  await Sentry.close()
})

describe('monitoring', () => {
  it('does not start without a DSN', () => {
    expect(initMonitoring('')).toBe(false)
  })

  it('redacts emails and tokens, and strips query strings', () => {
    expect(redact(`user ${EMAIL} sent ${JWT}`)).toBe('user [redacted] sent [redacted]')
    expect(stripQuery(`https://api.x/search?${LOCATION}&token=${JWT}#frag`)).toBe(
      'https://api.x/search',
    )
  })

  it('sends an error event with no email, token, location or console output', async () => {
    const sent = captureEnvelopes()

    Sentry.addBreadcrumb({
      category: 'fetch',
      data: { url: `https://api.ridematch.app/api/v1/search?${LOCATION}`, method: 'GET' },
    })
    Sentry.addBreadcrumb({ category: 'console', message: `logged ${EMAIL}` })
    Sentry.captureException(new Error(`Failed for ${EMAIL} with ${JWT}`))
    await Sentry.flush(2000)

    expect(sent.length).toBeGreaterThan(0)
    const text = sent.join('\n')
    for (const secret of [EMAIL, JWT, LOCATION, 'eyJ']) {
      expect(text, `${secret} reached Sentry`).not.toContain(secret)
    }
    expect(text).toContain('/api/v1/search')
  })
})
