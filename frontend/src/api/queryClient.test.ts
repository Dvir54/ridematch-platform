import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../mocks/node'
import { seedOnboardedMe } from '../mocks/db'
import { env } from '../env'
import { api } from './client'
import { sessionKey } from './keys'
import { createQueryClient } from './queryClient'

const base = env.apiBaseUrl.replace(/\/$/, '')

function forbid(code: string) {
  return HttpResponse.json({ code, message: 'No.' }, { status: 403 })
}

describe('query client', () => {
  it.each(['ONBOARDING_REQUIRED', 'ACCOUNT_DEACTIVATED'])(
    're-reads the session when any call answers %s',
    async (code) => {
      const client = createQueryClient()
      client.setQueryData(sessionKey, { status: 'ready', user: seedOnboardedMe() })
      server.use(http.get(`${base}/users/1`, () => forbid(code)))

      await client
        .fetchQuery({ queryKey: ['public-user', 1], queryFn: () => api.get('/users/1') })
        .catch(() => undefined)

      expect(client.getQueryState(sessionKey)?.isInvalidated).toBe(true)
    },
  )

  it('leaves the session alone for an unrelated failure', async () => {
    const client = createQueryClient()
    client.setQueryData(sessionKey, { status: 'ready', user: seedOnboardedMe() })
    server.use(http.get(`${base}/users/1`, () => forbid('FORBIDDEN')))

    await client
      .fetchQuery({ queryKey: ['public-user', 1], queryFn: () => api.get('/users/1') })
      .catch(() => undefined)

    expect(client.getQueryState(sessionKey)?.isInvalidated).toBe(false)
  })
})
