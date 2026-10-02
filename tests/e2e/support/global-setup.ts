import { clerkSetup } from '@clerk/testing/playwright'
import { CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY } from '../env'

export default async function globalSetup() {
  if (!CLERK_SECRET_KEY || !CLERK_PUBLISHABLE_KEY) {
    throw new Error('E2E needs CLERK_SECRET_KEY and VITE_CLERK_PUBLISHABLE_KEY in the root .env')
  }
  await clerkSetup({ publishableKey: CLERK_PUBLISHABLE_KEY, secretKey: CLERK_SECRET_KEY })
}
