import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/** Used by the Vitest setup file so component tests hit the same mock API. */
export const server = setupServer(...handlers)
