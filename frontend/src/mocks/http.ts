import { HttpResponse } from 'msw'
import type { ApiErrorBody } from '../api/types'

export function fail(
  status: number,
  code: string,
  message: string,
  details?: ApiErrorBody['details'],
) {
  const body: ApiErrorBody = { code, message }
  if (details) body.details = details
  return HttpResponse.json(body, { status })
}

/** The mock has no Clerk; any bearer token counts as a signed-in caller. */
export function signedIn(request: Request): boolean {
  return (request.headers.get('Authorization') ?? '').startsWith('Bearer ')
}

export const unauthenticated = () =>
  fail(401, 'UNAUTHENTICATED', 'Missing or invalid session token.')

export const onboardingRequired = () =>
  fail(403, 'ONBOARDING_REQUIRED', 'Complete onboarding to use RideMatch.')

export const forbidden = () => fail(403, 'FORBIDDEN', 'This is not yours.')

export const notFound = (what: string) => fail(404, 'NOT_FOUND', `No such ${what}.`)

export const conflict = (code: string, message: string) => fail(409, code, message)

/** `?status=upcoming,full` — the comma-separated filter from CONTRACT §2. */
export function statusFilter(url: URL): string[] | null {
  const raw = url.searchParams.get('status')
  if (!raw) return null
  const values = raw.split(',').map((value) => value.trim()).filter(Boolean)
  return values.length ? values : null
}

export function paginate<T>(rows: T[], url: URL): T[] {
  const limit = Math.min(Number(url.searchParams.get('limit') ?? 20) || 20, 100)
  const offset = Number(url.searchParams.get('offset') ?? 0) || 0
  return rows.slice(offset, offset + limit)
}
