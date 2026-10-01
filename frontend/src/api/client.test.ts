import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../mocks/node'
import { env } from '../env'
import { api } from './client'
import { ApiError, isApiError, messageFor } from './errors'

const base = env.apiBaseUrl.replace(/\/$/, '')

describe('api client', () => {
  it('sends the Clerk session token as a bearer token', async () => {
    let seen: string | null = null
    server.use(
      http.get(`${base}/users/me`, ({ request }) => {
        seen = request.headers.get('Authorization')
        return HttpResponse.json({ ok: true })
      }),
    )

    await api.get('/users/me')
    expect(seen).toBe('Bearer test-clerk-token')
  })

  it('turns the error envelope into an ApiError carrying the code', async () => {
    server.use(
      http.get(`${base}/users/me`, () =>
        HttpResponse.json(
          { code: 'ONBOARDING_REQUIRED', message: 'No profile yet' },
          { status: 403 },
        ),
      ),
    )

    const error = await api.get('/users/me').catch((caught: unknown) => caught)
    expect(isApiError(error)).toBe(true)
    expect((error as ApiError).code).toBe('ONBOARDING_REQUIRED')
    expect((error as ApiError).status).toBe(403)
  })

  it('exposes field errors from a 422 by their contract field name', async () => {
    server.use(
      http.post(`${base}/users/me/onboarding`, () =>
        HttpResponse.json(
          {
            code: 'VALIDATION_ERROR',
            message: 'Invalid',
            details: [{ field: 'body.date_of_birth', message: 'Must be 18 or older.' }],
          },
          { status: 422 },
        ),
      ),
    )

    const error = (await api
      .post('/users/me/onboarding', {})
      .catch((caught: unknown) => caught)) as ApiError
    expect(error.fieldError('date_of_birth')).toBe('Must be 18 or older.')
  })

  it('returns nothing for a 204', async () => {
    server.use(http.delete(`${base}/notifications`, () => new HttpResponse(null, { status: 204 })))
    await expect(api.delete('/notifications')).resolves.toBeUndefined()
  })

  it('reports an unreachable server as NETWORK_ERROR', async () => {
    server.use(http.get(`${base}/health`, () => HttpResponse.error()))

    const error = (await api.get('/health').catch((caught: unknown) => caught)) as ApiError
    expect(error.code).toBe('NETWORK_ERROR')
    expect(messageFor(error)).toContain('Check your connection')
  })
})
