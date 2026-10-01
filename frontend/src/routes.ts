import type { Mode } from './api/types'

export const paths = {
  welcome: '/',
  signIn: '/sign-in',
  signUp: '/sign-up',
  onboarding: '/onboarding',
  role: '/role',
  app: '/app',
  driverHome: '/app/driver',
  driverRides: '/app/driver/rides',
  driverRequests: '/app/driver/requests',
  passengerHome: '/app/passenger',
  passengerSearch: '/app/passenger/search',
  passengerTrips: '/app/passenger/trips',
  notifications: '/app/notifications',
  profile: '/app/profile',
} as const

export function homePathFor(mode: Mode): string {
  return mode === 'driver' ? paths.driverHome : paths.passengerHome
}

/**
 * Notifications and Profile are shared by both modes, so the URL alone cannot
 * always say which nav to show. The user's saved mode decides those.
 */
export function modeFromPath(pathname: string, fallback: Mode): Mode {
  if (pathname.startsWith(paths.driverHome)) return 'driver'
  if (pathname.startsWith(paths.passengerHome)) return 'passenger'
  return fallback
}
