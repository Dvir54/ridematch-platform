import { config } from 'dotenv'
import { resolve } from 'node:path'

// The repo-root .env is the one shared source of Clerk keys. Loading it here is
// runtime config for the test process; nothing in it is echoed or committed.
config({ path: resolve(import.meta.dirname, '../../.env'), quiet: true })

export const CLERK_SECRET_KEY = process.env.CLERK_SECRET_KEY ?? ''
export const CLERK_PUBLISHABLE_KEY = process.env.VITE_CLERK_PUBLISHABLE_KEY ?? ''

// Clerk's own helpers read these two names.
process.env.CLERK_PUBLISHABLE_KEY = CLERK_PUBLISHABLE_KEY

/** 127.0.0.1, not localhost: Docker's IPv6 forward hangs on the dev machine. */
export const TEST_DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  'postgresql+asyncpg://ridematch:ridematch@127.0.0.1:5434/ridematch_test'
export const REDIS_URL = process.env.E2E_REDIS_URL ?? 'redis://127.0.0.1:6379/14'
