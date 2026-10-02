import { http, HttpResponse } from 'msw'
import { env } from '../env'
import { isAdult } from '../lib/dates'
import { isValidPhone, PHONE_HINT } from '../lib/phone'
import type {
  OnboardingRequest,
  UserMe,
  UserPreferences,
  UserPreferencesPatch,
  UserStats,
  UserUpdate,
} from '../api/types'
import { adminHandlers } from './adminHandlers'
import { db, defaultNotifications, defaultPreferences, findUser } from './db'
import { conflict, fail, onboardingRequired, notFound, signedIn, unauthenticated } from './http'
import { mapboxHandlers } from './mapboxHandlers'
import { notificationHandlers } from './notificationHandlers'
import { toPublic } from './project'
import { ratingHandlers } from './ratingHandlers'
import { requestHandlers } from './requestHandlers'
import { rideHandlers } from './rideHandlers'
import { searchHandlers } from './searchHandlers'

const base = env.apiBaseUrl.replace(/\/$/, '')

/** openapi.yaml shares one `Phone` primitive across onboarding and PATCH. */
const badPhone = () =>
  fail(422, 'VALIDATION_ERROR', 'Request failed validation.', [
    { field: 'body.phone', message: PHONE_HINT },
  ])

/**
 * Preferences shallow-merge, and the `notifications` sub-object merges too
 * (CONTRACT §4) — so a patch naming one key never drops the others.
 */
function mergePreferences(
  current: UserPreferences,
  patch: UserPreferencesPatch | undefined,
): UserPreferences {
  return {
    ...current,
    ...patch,
    notifications: {
      ...defaultNotifications,
      ...current.notifications,
      ...patch?.notifications,
    },
  }
}

const userHandlers = [
  http.get(`${base}/health`, () =>
    HttpResponse.json({ status: 'ok', db: true, redis: true }),
  ),

  http.get(`${base}/users/me`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    if (!db.me.is_active) {
      return fail(403, 'ACCOUNT_DEACTIVATED', 'This account is deactivated.')
    }
    return HttpResponse.json(db.me)
  }),

  http.post(`${base}/users/me/onboarding`, async ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (db.me) return fail(409, 'ALREADY_ONBOARDED', 'This profile already exists.')

    const body = (await request.json()) as OnboardingRequest
    // The backend takes real JSON booleans only; a truthy string is a 422 there.
    if (body.accepted_terms !== true) {
      return fail(422, 'TERMS_NOT_ACCEPTED', 'You must accept the terms of service.', [
        { field: 'body.accepted_terms', message: 'Acceptance is required.' },
      ])
    }
    if (body.phone !== null && body.phone !== undefined && !isValidPhone(body.phone)) {
      return badPhone()
    }
    if (!isAdult(body.date_of_birth)) {
      return fail(422, 'UNDERAGE', 'You must be 18 or older.', [
        { field: 'body.date_of_birth', message: 'Must be 18 or older.' },
      ])
    }

    db.me = {
      id: 1,
      email: 'you@example.com',
      name: body.name,
      phone: body.phone ?? null,
      date_of_birth: body.date_of_birth,
      gender: body.gender ?? null,
      is_admin: false,
      is_active: true,
      driver_rating: null,
      driver_rating_count: 0,
      passenger_rating: null,
      passenger_rating_count: 0,
      preferences: mergePreferences(defaultPreferences, body.preferences),
      vehicle: body.vehicle ?? null,
      created_at: new Date().toISOString(),
      last_login_at: new Date().toISOString(),
    }
    return HttpResponse.json(db.me, { status: 201 })
  }),

  http.patch(`${base}/users/me`, async ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const patch = (await request.json()) as UserUpdate
    if (patch.phone !== null && patch.phone !== undefined && !isValidPhone(patch.phone)) {
      return badPhone()
    }
    if (
      patch.vehicle === null &&
      db.rides.some(
        (row) => row.driver_id === me.id && (row.status === 'upcoming' || row.status === 'full'),
      )
    ) {
      return conflict('VEHICLE_REQUIRED', 'Remove your upcoming rides before removing your car.')
    }

    const { preferences, ...rest } = patch
    db.me = {
      ...me,
      ...rest,
      preferences: mergePreferences(me.preferences, preferences),
    }
    return HttpResponse.json(db.me)
  }),

  http.get(`${base}/users/me/stats`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const myRides = db.rides.filter((row) => row.driver_id === me.id)
    const myRideIds = new Set(myRides.map((row) => row.id))
    const myRequests = db.requests.filter((row) => row.passenger_id === me.id)

    const stats: UserStats = {
      as_driver: {
        rides_offered: myRides.length,
        rides_completed: myRides.filter((row) => row.status === 'completed').length,
        upcoming_rides: myRides.filter((row) => row.status === 'upcoming' || row.status === 'full')
          .length,
        pending_requests: db.requests.filter(
          (row) => myRideIds.has(row.ride_id) && row.status === 'pending',
        ).length,
        passengers_carried: myRides
          .filter((row) => row.status === 'completed')
          .reduce(
            (total, row) =>
              total +
              db.requests
                .filter((req) => req.ride_id === row.id && req.status === 'approved')
                .reduce((seats, req) => seats + req.seats_requested, 0),
            0,
          ),
      },
      as_passenger: {
        trips_requested: myRequests.length,
        trips_completed: myRequests.filter((row) => {
          const ride = db.rides.find((candidate) => candidate.id === row.ride_id)
          return row.status === 'approved' && ride?.status === 'completed'
        }).length,
        upcoming_trips: myRequests.filter((row) => {
          const ride = db.rides.find((candidate) => candidate.id === row.ride_id)
          return (
            row.status === 'approved' &&
            (ride?.status === 'upcoming' || ride?.status === 'full' || ride?.status === 'in_progress')
          )
        }).length,
      },
    }
    return HttpResponse.json(stats)
  }),

  http.get(`${base}/users/:userId`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    const user: UserMe | undefined = findUser(Number(params.userId))
    if (!user) return notFound('user')
    return HttpResponse.json(toPublic(user))
  }),
]

export const handlers = [
  ...userHandlers,
  ...rideHandlers,
  ...requestHandlers,
  ...ratingHandlers,
  ...searchHandlers,
  ...notificationHandlers,
  ...adminHandlers,
  ...mapboxHandlers,
]
