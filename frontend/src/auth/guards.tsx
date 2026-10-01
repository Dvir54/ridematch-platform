import { useAuth, useClerk } from '@clerk/clerk-react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../api/hooks/users'
import { messageFor } from '../api/errors'
import { Button } from '../components/Button'
import { FullScreenLoader, MessageScreen } from '../components/states'
import { CurrentUserProvider } from './CurrentUserProvider'
import { useCurrentUser } from './currentUserContext'

/** Clerk session required. Anonymous visitors go to sign-in. */
export function RequireSignedIn() {
  const { isLoaded, isSignedIn } = useAuth()
  const location = useLocation()

  if (!isLoaded) return <FullScreenLoader label="Checking your session" />
  if (!isSignedIn) return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />
  return <Outlet />
}

function DeactivatedScreen() {
  const { signOut } = useClerk()
  return (
    <MessageScreen
      title="This account is deactivated"
      body="An administrator turned off access to RideMatch. Contact support to have it restored."
      action={
        <Button variant="secondary" onClick={() => void signOut()}>
          Sign out
        </Button>
      }
    />
  )
}

/**
 * A RideMatch profile required. A valid Clerk user without one gets
 * 403 ONBOARDING_REQUIRED and is sent to the onboarding form (CONTRACT §2).
 */
export function RequireProfile() {
  const { isSignedIn } = useAuth()
  const session = useSession(Boolean(isSignedIn))

  if (session.isPending) return <FullScreenLoader label="Loading your profile" />

  if (session.isError) {
    return (
      <MessageScreen
        title="Your profile did not load"
        body={messageFor(session.error)}
        action={<Button onClick={() => void session.refetch()}>Try again</Button>}
      />
    )
  }

  if (session.data.status === 'onboarding_required') return <Navigate to="/onboarding" replace />
  if (session.data.status === 'deactivated') return <DeactivatedScreen />

  return (
    <CurrentUserProvider user={session.data.user}>
      <Outlet />
    </CurrentUserProvider>
  )
}

/** A mode must be chosen before the app has a home to show. */
export function RequireMode() {
  const user = useCurrentUser()
  if (!user.preferences.default_mode) return <Navigate to="/role" replace />
  return <Outlet />
}

/** Admin screens are hidden here and enforced again by the backend. */
export function RequireAdmin() {
  const user = useCurrentUser()
  if (!user.is_admin) return <Navigate to="/app" replace />
  return <Outlet />
}
