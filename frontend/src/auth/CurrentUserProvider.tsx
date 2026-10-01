import type { ReactNode } from 'react'
import type { UserMe } from '../api/types'
import { CurrentUserContext } from './currentUserContext'

export function CurrentUserProvider({ user, children }: { user: UserMe; children: ReactNode }) {
  return <CurrentUserContext value={user}>{children}</CurrentUserContext>
}
