import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from '../mocks/node'
import { resetMockDb } from '../mocks/db'
import { setTokenProvider } from '../api/client'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterEach(() => {
  cleanup()
  server.resetHandlers()
  resetMockDb()
})

afterAll(() => server.close())

// Every test runs as a signed-in caller unless a test says otherwise.
setTokenProvider(async () => 'test-clerk-token')
