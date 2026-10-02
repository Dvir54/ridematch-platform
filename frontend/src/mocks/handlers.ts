import { http, HttpResponse } from 'msw'
import { env } from '../env'
import { isAdult } from '../lib/dates'
import { isValidPhone, PHONE_HINT } from '../lib/phone'
import type {
  OnboardingRequest,
  UserMe,
  UserPreferences,
  UserPreferencesPatch,
  UserUpdate,
} from '../api/types'
import { db, defaultNotifications, defaultPreferences, findUser } from './db'
import { fail, onboardingRequired, notFound, signedIn, unauthenticated } from './http'
import { mapboxHandlers } from './mapboxHandlers'
import { toPublic } from './project'
import { requestHandlers } from './requestHandlers'
import { rideHandlers } from './rideHandlers'

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

    const patch = (await request.json()) as UserUpdate
    if (patch.phone !== null && patch.phone !== undefined && !isValidPhone(patch.phone)) {
      return badPhone()
    }

    const { preferences, ...rest } = patch
    db.me = {
      ...db.me,
      ...rest,
      preferences: mergePreferences(db.me.preferences, preferences),
    }
    return HttpResponse.json(db.me)
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
  ...mapboxHandlers,
]
