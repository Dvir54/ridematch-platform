import { http, HttpResponse } from 'msw'
import { env } from '../env'
import { isAdult } from '../lib/dates'
import type {
  ApiErrorBody,
  OnboardingRequest,
  UserMe,
  UserPatch,
  UserPublic,
} from '../api/types'
import { db, defaultPreferences } from './db'

const base = env.apiBaseUrl.replace(/\/$/, '')

function fail(status: number, code: string, message: string, details?: ApiErrorBody['details']) {
  const body: ApiErrorBody = { code, message }
  if (details) body.details = details
  return HttpResponse.json(body, { status })
}

/** The mock has no Clerk; any bearer token counts as a signed-in caller. */
function signedIn(request: Request): boolean {
  return (request.headers.get('Authorization') ?? '').startsWith('Bearer ')
}

const unauthenticated = () =>
  fail(401, 'UNAUTHENTICATED', 'Missing or invalid session token.')

function toPublic(user: UserMe): UserPublic {
  return {
    id: user.id,
    name: user.name,
    driver_rating: user.driver_rating ?? null,
    driver_rating_count: user.driver_rating_count,
    passenger_rating: user.passenger_rating ?? null,
    passenger_rating_count: user.passenger_rating_count,
    vehicle: user.vehicle
      ? { make: user.vehicle.make, model: user.vehicle.model, color: user.vehicle.color }
      : null,
    created_at: user.created_at,
  }
}

export const handlers = [
  http.get(`${base}/health`, () =>
    HttpResponse.json({ status: 'ok', db: true, redis: true }),
  ),

  http.get(`${base}/users/me`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) {
      return fail(403, 'ONBOARDING_REQUIRED', 'Complete onboarding to use RideMatch.')
    }
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
      preferences: { ...defaultPreferences, ...body.preferences },
      vehicle: body.vehicle ?? null,
      created_at: new Date().toISOString(),
      last_login_at: new Date().toISOString(),
    }
    return HttpResponse.json(db.me, { status: 201 })
  }),

  http.patch(`${base}/users/me`, async ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return fail(403, 'ONBOARDING_REQUIRED', 'Complete onboarding first.')

    const patch = (await request.json()) as UserPatch
    const { preferences, ...rest } = patch
    db.me = {
      ...db.me,
      ...rest,
      preferences: {
        ...db.me.preferences,
        ...preferences,
        notifications: {
          ...(db.me.preferences.notifications ?? defaultPreferences.notifications),
          ...preferences?.notifications,
        },
      },
    } as UserMe
    return HttpResponse.json(db.me)
  }),

  http.get(`${base}/users/:userId`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    const id = Number(params.userId)
    const user = [db.me, ...db.users].find((candidate) => candidate?.id === id)
    if (!user) return fail(404, 'NOT_FOUND', 'No such user.')
    return HttpResponse.json(toPublic(user))
  }),
]
