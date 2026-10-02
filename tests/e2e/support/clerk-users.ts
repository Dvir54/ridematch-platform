import { createClerkClient } from '@clerk/backend'
import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright'
import type { Page } from '@playwright/test'
import { CLERK_SECRET_KEY } from '../env'

const client = createClerkClient({ secretKey: CLERK_SECRET_KEY })

export interface TestUser {
  id: string
  email: string
  name: string
}

/**
 * A fresh Clerk dev-instance user. `+clerk_test` addresses are Clerk's reserved
 * test emails (never delivered), and creating through the Backend API leaves the
 * address verified. No password is set, so there is nothing to store.
 */
export async function createTestUser(label: string): Promise<TestUser> {
  const stamp = Date.now().toString(36)
  const email = `e2e-${label}-${stamp}+clerk_test@example.com`
  const user = await client.users.createUser({
    emailAddress: [email],
    firstName: `E2E${label}${stamp}`,
    lastName: 'Rider',
    skipPasswordRequirement: true,
  })
  return { id: user.id, email, name: `E2E${label}${stamp} Rider` }
}

export async function deleteTestUser(user: TestUser) {
  await client.users.deleteUser(user.id).catch(() => undefined)
}

/** Signs `user` in on `page` through a Clerk sign-in ticket: no UI, no password. */
export async function signInAs(page: Page, user: TestUser) {
  await setupClerkTestingToken({ page })
  await page.goto('/')
  await clerk.signIn({ page, emailAddress: user.email })
}
