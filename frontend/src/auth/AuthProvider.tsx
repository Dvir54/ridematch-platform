import type { ReactNode } from 'react'
import { ClerkProvider } from '@clerk/clerk-react'
import { useNavigate } from 'react-router-dom'
import { env } from '../env'
import { ConfigurationNeeded } from '../components/states'

/**
 * Clerk owns sign-up, sign-in, email verification and sessions (CONTRACT §2).
 * It is mounted inside the router so its own redirects use client navigation.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()

  if (!env.clerkPublishableKey.startsWith('pk_')) {
    return <ConfigurationNeeded variable="VITE_CLERK_PUBLISHABLE_KEY" />
  }

  return (
    <ClerkProvider
      publishableKey={env.clerkPublishableKey}
      afterSignOutUrl="/"
      routerPush={(to) => navigate(to)}
      routerReplace={(to) => navigate(to, { replace: true })}
    >
      {children}
    </ClerkProvider>
  )
}
