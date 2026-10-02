import { http, HttpResponse } from 'msw'
import { env } from '../env'
import { db, toNotification } from './db'
import type { NotificationRow } from './db'
import { notFound, onboardingRequired, paginate, signedIn, unauthenticated } from './http'

const base = env.apiBaseUrl.replace(/\/$/, '')

const newestFirst = (a: NotificationRow, b: NotificationRow) =>
  b.created_at.localeCompare(a.created_at)

function mine(recipientId: number): NotificationRow[] {
  return db.notifications.filter((row) => row.recipient_id === recipientId).sort(newestFirst)
}

export const notificationHandlers = [
  http.get(`${base}/notifications`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const url = new URL(request.url)
    const unreadOnly = url.searchParams.get('unread_only') === 'true'
    const rows = mine(db.me.id).filter((row) => !unreadOnly || !row.is_read)

    return HttpResponse.json(paginate(rows, url).map(toNotification))
  }),

  http.delete(`${base}/notifications`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    db.notifications = db.notifications.filter((row) => row.recipient_id !== me.id)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get(`${base}/notifications/unread-count`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()

    const count = mine(db.me.id).filter((row) => !row.is_read).length
    return HttpResponse.json({ count })
  }),

  http.post(`${base}/notifications/:notificationId/read`, ({ request, params }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const row = db.notifications.find(
      (candidate) => candidate.id === Number(params.notificationId),
    )
    if (!row || row.recipient_id !== me.id) return notFound('notification')

    row.is_read = true
    return HttpResponse.json(toNotification(row))
  }),

  http.post(`${base}/notifications/read-all`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    for (const row of mine(me.id)) row.is_read = true
    return new HttpResponse(null, { status: 204 })
  }),
]
