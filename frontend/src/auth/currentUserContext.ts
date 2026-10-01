import { createContext, use } from 'react'
import type { UserMe } from '../api/types'

export const CurrentUserContext = createContext<UserMe | null>(null)

/** Only valid under `RequireProfile`, which guarantees an onboarded user. */
export function useCurrentUser(): UserMe {
  const user = use(CurrentUserContext)
  if (!user) {
    throw new Error('useCurrentUser must be used inside a route guarded by RequireProfile')
  }
  return user
}
