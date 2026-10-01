import { http, HttpResponse } from 'msw'
import { env } from '../env'
import { canStartYet } from '../lib/dates'
import type { RideCreate, RideUpdate } from '../api/types'
import { approvedSeats, db, defaultRidePreferences } from './db'
import type { RideRow } from './db'
import {
  conflict,
  fail,
  forbidden,
  notFound,
  onboardingRequired,
  paginate,
  signedIn,
  statusFilter,
  unauthenticated,
} from './http'
import { toRide, toRideRequest } from './project'

const base = env.apiBaseUrl.replace(/\/$/, '')

const LOCKED_FIELDS = [
  'start_lat',
  'start_lng',
  'start_address',
  'end_lat',
  'end_lng',
  'end_address',
  'departure_time',
] as const

/**
 * `available_seats = capacity − approved seats` must hold at all times, and the
 * ride flips between `upcoming` and `full` as that number hits zero or leaves it
 * (CONTRACT §3, §4). Terminal and in-progress rides are left alone.
 */
export function recomputeRideSeats(row: RideRow): void {
  row.available_seats = Math.max(0, row.capacity - approvedSeats(row.id))
  if (row.status === 'upcoming' || row.status === 'full') {
    row.status = row.available_seats === 0 ? 'full' : 'upcoming'
  }
}

export function touchRide(row: RideRow): void {
  row.updated_at = new Date().toISOString()
}

/** Cancelling or starting a ride resolves whatever requests were still open. */
function closeOpenRequests(rideId: number, outcome: 'cancelled' | 'rejected'): void {
  const now = new Date().toISOString()
  for (const request of db.requests) {
    if (request.ride_id !== rideId) continue
    if (outcome === 'cancelled' && (request.status === 'pending' || request.status === 'approved')) {
      request.status = 'cancelled'
      request.responded_at = now
    }
    if (outcome === 'rejected' && request.status === 'pending') {
      request.status = 'rejected'
      request.responded_at = now
    }
  }
}

export function findRideRow(rideId: number): RideRow | undefined {
  return db.rides.find((row) => row.id === rideId)
}

export const rideHandlers = [
  http.post(`${base}/rides`, async ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    if (!db.me.vehicle) {
      return conflict('VEHICLE_REQUIRED', 'Add a vehicle to your profile before offering a ride.')
    }

    const body = (await request.json()) as RideCreate
    if (new Date(body.departure_time).getTime() <= Date.now()) {
      return fail(422, 'DEPARTURE_IN_PAST', 'Departure time must be in the future.', [
        { field: 'body.departure_time', message: 'Must be in the future.' },
      ])
    }

    const now = new Date().toISOString()
    const row: RideRow = {
      id: db.nextRideId++,
      driver_id: db.me.id,
      start_lat: body.start_lat,
      start_lng: body.start_lng,
      start_address: body.start_address,
      end_lat: body.end_lat,
      end_lng: body.end_lng,
      end_address: body.end_address,
      departure_time: body.departure_time,
      capacity: body.capacity,
      available_seats: body.capacity,
      price_per_seat: body.price_per_seat,
      // On create the server fills the four defaults, then applies what was sent.
      preferences: { ...defaultRidePreferences, ...body.preferences },
      status: 'upcoming',
      notes: body.notes ?? null,
      created_at: now,
      updated_at: now,
    }
    db.rides.push(row)
    return HttpResponse.json(toRide(row, db.me.id), { status: 201 })
  }),

  http.get(`${base}/rides/mine`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const url = new URL(request.url)
    const statuses = statusFilter(url)
    const mine = db.rides
      .filter((row) => row.driver_id === me.id)
      .filter((row) => !statuses || statuses.includes(row.status))
      .sort((a, b) => a.departure_time.localeCompare(b.departure_time))

    return HttpResponse.json(paginate(mine, url).map((row) => toRide(row, me.id)))
  }),

  http.get(`${base}/rides/:rideId`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    return HttpResponse.json(toRide(row, db.me.id))
  }),

  http.patch(`${base}/rides/:rideId`, async ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    if (row.driver_id !== db.me.id) return forbidden()
    if (row.status !== 'upcoming' && row.status !== 'full') {
      return conflict('INVALID_STATE_TRANSITION', `A ${row.status} ride cannot be edited.`)
    }

    const patch = (await request.json()) as RideUpdate
    const taken = approvedSeats(row.id)

    if (taken > 0 && LOCKED_FIELDS.some((field) => patch[field] !== undefined)) {
      return conflict(
        'RIDE_HAS_APPROVED_PASSENGERS',
        'The route and departure time are locked once a passenger is approved.',
      )
    }
    if (patch.capacity !== undefined && patch.capacity < taken) {
      return conflict('CAPACITY_BELOW_APPROVED', `You have already approved ${taken} seats.`)
    }

    const { preferences, ...rest } = patch
    Object.assign(row, rest)
    // Shallow merge, absent keys left alone (D16).
    if (preferences) row.preferences = { ...row.preferences, ...preferences }

    recomputeRideSeats(row)
    touchRide(row)
    return HttpResponse.json(toRide(row, db.me.id))
  }),

  http.post(`${base}/rides/:rideId/cancel`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    if (row.driver_id !== db.me.id) return forbidden()
    if (row.status !== 'upcoming' && row.status !== 'full') {
      return conflict('INVALID_STATE_TRANSITION', `A ${row.status} ride cannot be cancelled.`)
    }

    row.status = 'cancelled'
    closeOpenRequests(row.id, 'cancelled')
    touchRide(row)
    return HttpResponse.json(toRide(row, db.me.id))
  }),

  http.post(`${base}/rides/:rideId/start`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    if (row.driver_id !== db.me.id) return forbidden()
    if (row.status !== 'upcoming' && row.status !== 'full') {
      return conflict('INVALID_STATE_TRANSITION', `A ${row.status} ride cannot be started.`)
    }
    if (!canStartYet(row.departure_time)) {
      return conflict('TOO_EARLY_TO_START', 'A ride can start two hours before departure.')
    }

    row.status = 'in_progress'
    closeOpenRequests(row.id, 'rejected')
    touchRide(row)
    return HttpResponse.json(toRide(row, db.me.id))
  }),

  http.post(`${base}/rides/:rideId/complete`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    if (row.driver_id !== db.me.id) return forbidden()
    if (row.status !== 'in_progress') {
      return conflict('INVALID_STATE_TRANSITION', 'Only a ride in progress can be completed.')
    }

    row.status = 'completed'
    touchRide(row)
    return HttpResponse.json(toRide(row, db.me.id))
  }),

  http.get(`${base}/rides/:rideId/requests`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    if (row.driver_id !== me.id) return forbidden()

    const status = new URL(request.url).searchParams.get('status')
    const rows = db.requests
      .filter((candidate) => candidate.ride_id === row.id)
      .filter((candidate) => !status || candidate.status === status)
      .sort((a, b) => b.requested_at.localeCompare(a.requested_at))

    return HttpResponse.json(rows.map((candidate) => toRideRequest(candidate, me.id)))
  }),
]
