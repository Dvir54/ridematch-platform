import type { Mode } from './api/types'

/**
 * Every ride screen lives under the mode it belongs to, so the URL alone decides
 * which bottom nav is showing. The same ride therefore has two addresses — the
 * driver's and the passenger's — and each screen sends you to the other one if
 * you arrive at the wrong half.
 */
export const paths = {
  welcome: '/',
  signIn: '/sign-in',
  signUp: '/sign-up',
  onboarding: '/onboarding',
  role: '/role',
  app: '/app',

  driverHome: '/app/driver',
  driverRides: '/app/driver/rides',
  createRide: '/app/driver/rides/new',
  driverRide: (rideId: number) => `/app/driver/rides/${rideId}`,
  editRide: (rideId: number) => `/app/driver/rides/${rideId}/edit`,
  driverRequests: '/app/driver/requests',

  passengerHome: '/app/passenger',
  passengerSearch: '/app/passenger/search',
  passengerTrips: '/app/passenger/trips',
  passengerRide: (rideId: number) => `/app/passenger/rides/${rideId}`,

  notifications: '/app/notifications',
  profile: '/app/profile',
  user: (userId: number) => `/app/users/${userId}`,
  rate: (rideId: number, userId: number) => `/app/rate/${rideId}/${userId}`,
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
