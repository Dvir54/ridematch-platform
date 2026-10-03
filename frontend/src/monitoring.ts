import * as Sentry from '@sentry/react'
import type { Breadcrumb, ErrorEvent } from '@sentry/react'
import { env } from './env'

/**
 * Sentry, errors only (decision D2): no tracing, no session replay, no personal data.
 *
 * What could reach Sentry from the browser, and what stops it:
 * - the page URL and fetch/XHR breadcrumbs carry query strings (search lat/lng,
 *   addresses): stripped from every URL
 * - console breadcrumbs can carry whatever was logged: dropped
 * - error messages can quote an email or a token: redacted
 * - headers, cookies, bodies, query params and user info: `dataCollection` turns
 *   every category off, so neither the `Authorization` header nor the WebSocket
 *   `auth` token can be attached
 *
 * An empty `VITE_SENTRY_DSN` turns it off.
 */
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g
const JWT = /eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*/g
const REDACTED = '[redacted]'

export function redact(text: string): string {
  return text.replace(JWT, REDACTED).replace(EMAIL, REDACTED)
}

export function stripQuery(url: string): string {
  const cut = url.search(/[?#]/)
  return cut === -1 ? url : url.slice(0, cut)
}

export function scrubBreadcrumb(crumb: Breadcrumb): Breadcrumb | null {
  if (crumb.category === 'console') return null
  if (crumb.message) crumb.message = redact(crumb.message)
  if (crumb.data) {
    for (const key of ['url', 'from', 'to']) {
      const value = crumb.data[key]
      if (typeof value === 'string') crumb.data[key] = stripQuery(value)
    }
  }
  return crumb
}

export function scrubEvent(event: ErrorEvent): ErrorEvent {
  if (event.request) {
    event.request = { url: event.request.url ? stripQuery(event.request.url) : undefined }
  }
  delete event.user
  if (event.message) event.message = redact(event.message)
  for (const exception of event.exception?.values ?? []) {
    if (exception.value) exception.value = redact(exception.value)
  }
  if (event.breadcrumbs) {
    event.breadcrumbs = event.breadcrumbs
      .map((crumb) => scrubBreadcrumb(crumb))
      .filter((crumb): crumb is Breadcrumb => crumb !== null)
  }
  return event
}

/** Starts Sentry when a DSN is configured. `extra` is for tests (an in-memory transport). */
export function initMonitoring(
  dsn: string = env.sentryDsn,
  extra: Partial<Sentry.BrowserOptions> = {},
): boolean {
  if (!dsn) return false
  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    // SDK v11 collects every category by default; RideMatch collects none of them.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      graphQL: { document: false, variables: false },
      genAI: { inputs: false, outputs: false },
    },
    // Errors only: no tracing integration, no replay integration.
    tracesSampleRate: undefined,
    beforeSend: scrubEvent,
    beforeBreadcrumb: scrubBreadcrumb,
    ...extra,
  })
  return true
}

export function reportError(error: unknown, componentStack?: string | null): void {
  Sentry.captureException(error, componentStack ? { extra: { componentStack } } : undefined)
}
