import type { ApiErrorBody, FieldError } from './types'

/** Every `code` the backend can return — CONTRACT.md §5. */
export const API_ERROR_CODES = [
  'INVALID_WEBHOOK_SIGNATURE',
  'UNAUTHENTICATED',
  'ONBOARDING_REQUIRED',
  'ACCOUNT_DEACTIVATED',
  'FORBIDDEN',
  'NOT_A_PARTICIPANT',
  'NOT_FOUND',
  'ALREADY_ONBOARDED',
  'EMAIL_ALREADY_EXISTS',
  'INVALID_STATE_TRANSITION',
  'TOO_EARLY_TO_START',
  'RIDE_HAS_APPROVED_PASSENGERS',
  'CAPACITY_BELOW_APPROVED',
  'CANNOT_REQUEST_OWN_RIDE',
  'RIDE_NOT_OPEN',
  'NOT_ENOUGH_SEATS',
  'REQUEST_ALREADY_EXISTS',
  'PREVIOUSLY_REJECTED',
  'TOO_LATE_TO_CANCEL',
  'VEHICLE_REQUIRED',
  'RIDE_NOT_COMPLETED',
  'ALREADY_RATED',
  'CANNOT_DEACTIVATE_SELF',
  'VALIDATION_ERROR',
  'UNDERAGE',
  'TERMS_NOT_ACCEPTED',
  'DEPARTURE_IN_PAST',
] as const

export type ApiErrorCode = (typeof API_ERROR_CODES)[number]

/** Codes the client raises itself; the backend never sends these. */
export type ClientErrorCode = 'NETWORK_ERROR' | 'UNEXPECTED_RESPONSE'

export type ErrorCode = ApiErrorCode | ClientErrorCode | (string & {})

/**
 * Thrown by every call in `client.ts`. Screens branch on `code`, never on
 * `message` — the message is for people, the code is for logic.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: ErrorCode
  readonly details: FieldError[]

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details ?? []
  }

  is(...codes: ErrorCode[]): boolean {
    return codes.includes(this.code)
  }

  /** The message for a single form field, if the backend named one. */
  fieldError(field: string): string | undefined {
    const match = this.details.find((d) => d.field === field || d.field === `body.${field}`)
    return match?.message
  }

  /**
   * A detail that names the whole body rather than a field, so no input can be
   * highlighted from it. PATCH /rides/{id} currently answers `field: "body"` for a
   * null-valued 422 where POST /rides names the field (found by @tests), so a form
   * that only maps details to inputs would swallow the reason entirely.
   */
  formError(): string | undefined {
    const match = this.details.find((d) => !d.field || d.field === 'body')
    return match?.message
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

/**
 * What a person reads when something fails. Written in the interface's voice:
 * what happened, and what to do about it.
 */
const MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: 'Your session expired. Sign in again to continue.',
  ONBOARDING_REQUIRED: 'Finish setting up your profile first.',
  ACCOUNT_DEACTIVATED: 'This account is deactivated. Contact support to get it back.',
  FORBIDDEN: "This isn't yours to change.",
  NOT_A_PARTICIPANT: 'You can only rate people you actually rode with.',
  NOT_FOUND: "That's gone — it may have been cancelled or deleted.",
  ALREADY_ONBOARDED: 'Your profile is already set up.',
  EMAIL_ALREADY_EXISTS: 'Another profile already uses this email address.',
  INVALID_STATE_TRANSITION: "This ride has moved on; that action no longer applies.",
  TOO_EARLY_TO_START: 'You can start a ride up to two hours before departure.',
  RIDE_HAS_APPROVED_PASSENGERS:
    'Passengers are already approved, so the route and time are locked. Cancel the ride if the plan changed.',
  CAPACITY_BELOW_APPROVED: 'You already approved more seats than that. Raise the number or free a seat first.',
  CANNOT_REQUEST_OWN_RIDE: "You're driving this one.",
  RIDE_NOT_OPEN: 'This ride stopped taking requests.',
  NOT_ENOUGH_SEATS: "There aren't that many seats left.",
  REQUEST_ALREADY_EXISTS: 'You already have a request on this ride.',
  PREVIOUSLY_REJECTED: 'The driver turned down your request for this ride.',
  TOO_LATE_TO_CANCEL: 'Seats lock one hour before departure. Message the driver instead.',
  VEHICLE_REQUIRED: 'Add your car to your profile before offering a ride.',
  RIDE_NOT_COMPLETED: 'You can rate once the ride is complete.',
  ALREADY_RATED: 'You already rated this person for this ride.',
  CANNOT_DEACTIVATE_SELF: 'You cannot deactivate your own account.',
  VALIDATION_ERROR: 'Some details need fixing.',
  UNDERAGE: 'You must be 18 or older to use RideMatch.',
  TERMS_NOT_ACCEPTED: 'Accept the terms to continue.',
  DEPARTURE_IN_PAST: 'Pick a departure time in the future.',
  NETWORK_ERROR: "Can't reach RideMatch. Check your connection and try again.",
  UNEXPECTED_RESPONSE: 'Something went wrong on our side. Try again.',
}

/** A user-facing message for any thrown value. Always returns something. */
export function messageFor(error: unknown): string {
  if (isApiError(error)) {
    return MESSAGES[error.code] ?? error.message ?? MESSAGES.UNEXPECTED_RESPONSE
  }
  return MESSAGES.UNEXPECTED_RESPONSE
}
