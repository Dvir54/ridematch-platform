import { http, HttpResponse } from 'msw'
import { env } from '../env'
import type { PendingRating, RatingCreate, RoleRated } from '../api/types'
import { db, findUser } from './db'
import type { RatingRow, RideRow } from './db'
import { findRideRow } from './rideHandlers'
import {
  conflict,
  fail,
  notFound,
  onboardingRequired,
  paginate,
  signedIn,
  unauthenticated,
} from './http'
import { toPublic, toRating, toRide } from './project'

const base = env.apiBaseUrl.replace(/\/$/, '')

function approvedPassengerIds(rideId: number): number[] {
  return db.requests
    .filter((row) => row.ride_id === rideId && row.status === 'approved')
    .map((row) => row.passenger_id)
}

function alreadyRated(rideId: number, fromUserId: number, toUserId: number): boolean {
  return db.ratings.some(
    (row) => row.ride_id === rideId && row.from_user_id === fromUserId && row.to_user_id === toUserId,
  )
}

/** Cached-average update, in one step: `new = (old*count + score)/(count+1)` (CONTRACT §4). */
function applyRatingToCache(toUserId: number, roleRated: RoleRated, score: number): void {
  const ratee = findUser(toUserId)
  if (!ratee) return
  const avgKey = roleRated === 'driver' ? 'driver_rating' : 'passenger_rating'
  const countKey = roleRated === 'driver' ? 'driver_rating_count' : 'passenger_rating_count'
  const oldAverage = ratee[avgKey] ?? 0
  const oldCount = ratee[countKey]
  ratee[countKey] = oldCount + 1
  ratee[avgKey] = (oldAverage * oldCount + score) / (oldCount + 1)
}

function pendingRatingsFor(ride: RideRow, viewerId: number): PendingRating | null {
  const isDriver = ride.driver_id === viewerId
  const approved = approvedPassengerIds(ride.id)

  if (isDriver) {
    const unrated = approved.find((passengerId) => !alreadyRated(ride.id, viewerId, passengerId))
    if (unrated === undefined) return null
    const passenger = findUser(unrated)
    if (!passenger) return null
    return { ride: toRide(ride, viewerId), to_user: toPublic(passenger), role_rated: 'passenger' }
  }

  if (!approved.includes(viewerId)) return null
  if (alreadyRated(ride.id, viewerId, ride.driver_id)) return null
  const driver = findUser(ride.driver_id)
  if (!driver) return null
  return { ride: toRide(ride, viewerId), to_user: toPublic(driver), role_rated: 'driver' }
}

export const ratingHandlers = [
  http.post(`${base}/ratings`, async ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const body = (await request.json()) as RatingCreate
    const ride = findRideRow(body.ride_id)
    if (!ride) return notFound('ride')
    if (ride.status !== 'completed') {
      return conflict('RIDE_NOT_COMPLETED', 'You can rate once the ride is complete.')
    }

    const isDriver = ride.driver_id === me.id
    const approved = approvedPassengerIds(ride.id)
    const callerIsParticipant = isDriver || approved.includes(me.id)
    if (!callerIsParticipant || body.to_user_id === me.id) {
      return fail(403, 'NOT_A_PARTICIPANT', "You can only rate people you actually rode with.")
    }

    let roleRated: RoleRated
    if (isDriver) {
      if (!approved.includes(body.to_user_id)) {
        return fail(403, 'NOT_A_PARTICIPANT', "You can only rate people you actually rode with.")
      }
      roleRated = 'passenger'
    } else {
      if (body.to_user_id !== ride.driver_id) {
        return fail(403, 'NOT_A_PARTICIPANT', "You can only rate people you actually rode with.")
      }
      roleRated = 'driver'
    }

    if (alreadyRated(ride.id, me.id, body.to_user_id)) {
      return conflict('ALREADY_RATED', 'You already rated this person for this ride.')
    }

    const row: RatingRow = {
      id: db.nextRatingId++,
      ride_id: ride.id,
      from_user_id: me.id,
      to_user_id: body.to_user_id,
      role_rated: roleRated,
      score: body.score,
      comment: body.comment ?? null,
      tags: body.tags ?? [],
      created_at: new Date().toISOString(),
    }
    db.ratings.push(row)
    applyRatingToCache(body.to_user_id, roleRated, body.score)

    return HttpResponse.json(toRating(row), { status: 201 })
  }),

  http.get(`${base}/ratings/pending`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const rows = db.rides
      .filter((ride) => ride.status === 'completed')
      .map((ride) => pendingRatingsFor(ride, me.id))
      .filter((row): row is PendingRating => row !== null)

    return HttpResponse.json(rows)
  }),

  http.get(`${base}/users/:userId/ratings`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const userId = Number(params.userId)
    if (!findUser(userId)) return notFound('user')

    const url = new URL(request.url)
    const roleRated = url.searchParams.get('role_rated')
    const rows = db.ratings
      .filter((row) => row.to_user_id === userId)
      .filter((row) => !roleRated || row.role_rated === roleRated)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))

    return HttpResponse.json(paginate(rows, url).map(toRating))
  }),
]
