import { http, HttpResponse } from 'msw'
import { env } from '../env'
import type { AdminUserDetail, AnalyticsSummary, UserMe } from '../api/types'
import { db, findUser } from './db'
import { closeOpenRequests, findRideRow, touchRide } from './rideHandlers'
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
import { toRating, toRide, toRideRequest } from './project'

const base = env.apiBaseUrl.replace(/\/$/, '')

/** Every /admin/* handler needs the same three checks before the admin one. */
function requireAdmin(request: Request): UserMe | Response {
  if (!signedIn(request)) return unauthenticated()
  if (!db.me) return onboardingRequired()
  if (!db.me.is_active) return fail(403, 'ACCOUNT_DEACTIVATED', 'This account is deactivated.')
  if (!db.me.is_admin) return forbidden()
  return db.me
}

function isUserMe(value: UserMe | Response): value is UserMe {
  return !(value instanceof Response)
}

export const adminHandlers = [
  http.get(`${base}/admin/users`, ({ request }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const url = new URL(request.url)
    const q = url.searchParams.get('q')?.trim().toLowerCase()
    const isActiveParam = url.searchParams.get('is_active')
    const isAdminParam = url.searchParams.get('is_admin')

    let users = [db.me, ...db.users].filter((u): u is UserMe => Boolean(u))
    // Dedupe: `me` doubles as one of the seeded users in some test setups.
    users = [...new Map(users.map((u) => [u.id, u])).values()]

    if (q) {
      users = users.filter(
        (u) => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
      )
    }
    if (isActiveParam !== null) {
      const want = isActiveParam === 'true'
      users = users.filter((u) => u.is_active === want)
    }
    if (isAdminParam !== null) {
      const want = isAdminParam === 'true'
      users = users.filter((u) => u.is_admin === want)
    }
    users.sort((a, b) => a.id - b.id)

    return HttpResponse.json(paginate(users, url), {
      headers: { 'X-Total-Count': String(users.length) },
    })
  }),

  http.get(`${base}/admin/users/:userId`, ({ request, params }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const userId = Number(params.userId)
    const user = findUser(userId)
    if (!user) return notFound('user')

    const detail: AdminUserDetail = {
      user,
      rides_as_driver: db.rides
        .filter((row) => row.driver_id === userId)
        .map((row) => toRide(row, null)),
      requests_as_passenger: db.requests
        .filter((row) => row.passenger_id === userId)
        .map((row) => toRideRequest(row, userId)),
      ratings_received: db.ratings
        .filter((row) => row.to_user_id === userId)
        .map((row) => toRating(row)),
    }
    return HttpResponse.json(detail)
  }),

  http.post(`${base}/admin/users/:userId/deactivate`, ({ request, params }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const userId = Number(params.userId)
    const user = findUser(userId)
    if (!user) return notFound('user')
    if (userId === admin.id) return conflict('CANNOT_DEACTIVATE_SELF', 'You cannot deactivate your own account.')

    user.is_active = false
    return HttpResponse.json(user)
  }),

  http.post(`${base}/admin/users/:userId/reactivate`, ({ request, params }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const userId = Number(params.userId)
    const user = findUser(userId)
    if (!user) return notFound('user')

    user.is_active = true
    return HttpResponse.json(user)
  }),

  http.get(`${base}/admin/rides`, ({ request }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const url = new URL(request.url)
    const statuses = statusFilter(url)
    const driverId = url.searchParams.get('driver_id')
    const from = url.searchParams.get('from')
    const to = url.searchParams.get('to')

    let rides = db.rides
    if (statuses) rides = rides.filter((row) => statuses.includes(row.status))
    if (driverId) rides = rides.filter((row) => row.driver_id === Number(driverId))
    if (from) rides = rides.filter((row) => row.departure_time >= from)
    if (to) rides = rides.filter((row) => row.departure_time < to)
    rides = [...rides].sort((a, b) => a.departure_time.localeCompare(b.departure_time))

    return HttpResponse.json(
      paginate(rides, url).map((row) => toRide(row, null)),
      { headers: { 'X-Total-Count': String(rides.length) } },
    )
  }),

  http.post(`${base}/admin/rides/:rideId/force-cancel`, async ({ request, params }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const row = findRideRow(Number(params.rideId))
    if (!row) return notFound('ride')
    if (row.status === 'completed' || row.status === 'cancelled') {
      return conflict('INVALID_STATE_TRANSITION', `A ${row.status} ride cannot be cancelled.`)
    }

    const body = (await request.json()) as { reason?: string }
    if (!body.reason?.trim()) {
      return fail(422, 'VALIDATION_ERROR', 'Request failed validation.', [
        { field: 'body.reason', message: 'A reason is required.' },
      ])
    }

    row.status = 'cancelled'
    closeOpenRequests(row.id, 'cancelled')
    touchRide(row)
    return HttpResponse.json(toRide(row, null))
  }),

  http.get(`${base}/admin/analytics`, ({ request }) => {
    const admin = requireAdmin(request)
    if (!isUserMe(admin)) return admin

    const url = new URL(request.url)
    const from = url.searchParams.get('from')
    const to = url.searchParams.get('to')
    if (!from || !to) {
      return fail(422, 'VALIDATION_ERROR', 'Request failed validation.', [
        { field: 'query.from', message: 'Required.' },
      ])
    }

    const ridesInRange = db.rides.filter(
      (row) => row.departure_time >= from && row.departure_time < to,
    )
    const completed = ridesInRange.filter((row) => row.status === 'completed').length
    const cancelled = ridesInRange.filter((row) => row.status === 'cancelled').length

    const requestsInRange = db.requests.filter(
      (row) => row.requested_at >= from && row.requested_at < to,
    )
    const approved = requestsInRange.filter((row) => row.status === 'approved').length
    const rejected = requestsInRange.filter((row) => row.status === 'rejected').length

    const users = [db.me, ...db.users].filter((u): u is UserMe => Boolean(u))
    const summary: AnalyticsSummary = {
      from,
      to,
      rides_created: ridesInRange.length,
      rides_completed: completed,
      rides_cancelled: cancelled,
      completion_rate: completed + cancelled === 0 ? null : completed / (completed + cancelled),
      requests_created: requestsInRange.length,
      approval_rate: approved + rejected === 0 ? null : approved / (approved + rejected),
      active_users: users.filter(
        (u) => u.last_login_at && u.last_login_at >= from && u.last_login_at < to,
      ).length,
      new_users: users.filter((u) => u.created_at >= from && u.created_at < to).length,
    }
    return HttpResponse.json(summary)
  }),
]
