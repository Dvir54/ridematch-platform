import { http, HttpResponse } from 'msw'
import { env } from '../env'
import { canCancelApprovedYet } from '../lib/dates'
import type { RideRequestCreate } from '../api/types'
import { db } from './db'
import type { RequestRow } from './db'
import {
  conflict,
  forbidden,
  notFound,
  onboardingRequired,
  paginate,
  signedIn,
  statusFilter,
  unauthenticated,
} from './http'
import { toRideRequest } from './project'
import { findRideRow, recomputeRideSeats, touchRide } from './rideHandlers'

const base = env.apiBaseUrl.replace(/\/$/, '')

function findRequest(requestId: number): RequestRow | undefined {
  return db.requests.find((row) => row.id === requestId)
}

const newestFirst = (a: RequestRow, b: RequestRow) =>
  b.requested_at.localeCompare(a.requested_at)

export const requestHandlers = [
  http.post(`${base}/rides/:rideId/requests`, async ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const ride = findRideRow(Number(params.rideId))
    if (!ride) return notFound('ride')

    if (ride.driver_id === me.id) {
      return conflict('CANNOT_REQUEST_OWN_RIDE', 'You are driving this ride.')
    }
    if (ride.status !== 'upcoming') {
      return conflict('RIDE_NOT_OPEN', `This ride is ${ride.status}.`)
    }

    const mine = db.requests.filter(
      (row) => row.ride_id === ride.id && row.passenger_id === me.id,
    )
    if (mine.some((row) => row.status === 'pending' || row.status === 'approved')) {
      return conflict('REQUEST_ALREADY_EXISTS', 'You already have a request on this ride.')
    }
    // A driver's rejection is final for this ride; the passenger's own cancel is not (D2).
    if (mine.some((row) => row.status === 'rejected')) {
      return conflict('PREVIOUSLY_REJECTED', 'The driver already turned down this request.')
    }

    const body = ((await request.json()) ?? {}) as RideRequestCreate
    const seats = body.seats_requested ?? 1
    if (seats > ride.available_seats) {
      return conflict('NOT_ENOUGH_SEATS', `Only ${ride.available_seats} seats are left.`)
    }

    const row: RequestRow = {
      id: db.nextRequestId++,
      ride_id: ride.id,
      passenger_id: me.id,
      seats_requested: seats,
      status: 'pending',
      requested_at: new Date().toISOString(),
      responded_at: null,
    }
    db.requests.push(row)
    return HttpResponse.json(toRideRequest(row, me.id), { status: 201 })
  }),

  http.get(`${base}/requests/mine`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const url = new URL(request.url)
    const statuses = statusFilter(url)
    const mine = db.requests
      .filter((row) => row.passenger_id === me.id)
      .filter((row) => !statuses || statuses.includes(row.status))
      .sort(newestFirst)

    return HttpResponse.json(paginate(mine, url).map((row) => toRideRequest(row, me.id)))
  }),

  http.get(`${base}/requests/incoming`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const status = new URL(request.url).searchParams.get('status') ?? 'pending'
    const myRideIds = new Set(
      db.rides.filter((row) => row.driver_id === me.id).map((row) => row.id),
    )
    const incoming = db.requests
      .filter((row) => myRideIds.has(row.ride_id) && row.status === status)
      .sort(newestFirst)

    return HttpResponse.json(incoming.map((row) => toRideRequest(row, me.id)))
  }),

  http.get(`${base}/requests/:requestId`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const row = findRequest(Number(params.requestId))
    if (!row) return notFound('request')
    const ride = findRideRow(row.ride_id)
    if (row.passenger_id !== me.id && ride?.driver_id !== me.id) return forbidden()

    return HttpResponse.json(toRideRequest(row, me.id))
  }),

  http.post(`${base}/requests/:requestId/approve`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const row = findRequest(Number(params.requestId))
    if (!row) return notFound('request')
    const ride = findRideRow(row.ride_id)
    if (!ride) return notFound('ride')
    if (ride.driver_id !== me.id) return forbidden()
    if (row.status !== 'pending') {
      return conflict('INVALID_STATE_TRANSITION', `This request is already ${row.status}.`)
    }
    if (ride.status !== 'upcoming' && ride.status !== 'full') {
      return conflict('INVALID_STATE_TRANSITION', `This ride is ${ride.status}.`)
    }
    // The last seat can be gone between loading the list and pressing approve.
    if (row.seats_requested > ride.available_seats) {
      return conflict('NOT_ENOUGH_SEATS', `Only ${ride.available_seats} seats are left.`)
    }

    row.status = 'approved'
    row.responded_at = new Date().toISOString()
    recomputeRideSeats(ride)
    touchRide(ride)
    return HttpResponse.json(toRideRequest(row, me.id))
  }),

  http.post(`${base}/requests/:requestId/reject`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const row = findRequest(Number(params.requestId))
    if (!row) return notFound('request')
    const ride = findRideRow(row.ride_id)
    if (!ride) return notFound('ride')
    if (ride.driver_id !== me.id) return forbidden()
    if (row.status !== 'pending') {
      return conflict('INVALID_STATE_TRANSITION', `This request is already ${row.status}.`)
    }

    row.status = 'rejected'
    row.responded_at = new Date().toISOString()
    return HttpResponse.json(toRideRequest(row, me.id))
  }),

  http.post(`${base}/requests/:requestId/cancel`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const row = findRequest(Number(params.requestId))
    if (!row) return notFound('request')
    const ride = findRideRow(row.ride_id)
    if (!ride) return notFound('ride')
    if (row.passenger_id !== me.id) return forbidden()

    if (row.status === 'pending') {
      if (ride.status !== 'upcoming' && ride.status !== 'full') {
        return conflict('INVALID_STATE_TRANSITION', `This ride is ${ride.status}.`)
      }
    } else if (row.status === 'approved') {
      // Approved seats lock an hour before departure (D15).
      if (!canCancelApprovedYet(ride.departure_time)) {
        return conflict('TOO_LATE_TO_CANCEL', 'Approved seats lock an hour before departure.')
      }
    } else {
      return conflict('INVALID_STATE_TRANSITION', `This request is already ${row.status}.`)
    }

    row.status = 'cancelled'
    row.responded_at = new Date().toISOString()
    // The seats go back, and a full ride opens up again.
    recomputeRideSeats(ride)
    touchRide(ride)
    return HttpResponse.json(toRideRequest(row, me.id))
  }),
]
