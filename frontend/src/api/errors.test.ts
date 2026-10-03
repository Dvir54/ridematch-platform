import { describe, expect, it } from 'vitest'
import { API_ERROR_CODES, ApiError, messageFor } from './errors'

/**
 * Screens branch on `code`, never on `message` (CONTRACT §2) — which only works
 * if every code a screen can hit has a message written for it. An unmapped code
 * falls through to the server's own English, which is not written for readers.
 */
const FALLBACK = 'Something went wrong on our side. Try again.'

const error = (code: string) =>
  new ApiError(409, { code, message: 'raw server text nobody should read' })

/**
 * Codes no screen can ever hit: Svix calls `/webhooks/clerk` directly, and only the
 * host's health check calls `/ready`, so a browser is never on either path.
 */
const NEVER_SEEN_BY_A_SCREEN = ['INVALID_WEBHOOK_SIGNATURE', 'NOT_READY']

describe('error messages', () => {
  it('has a written message for every code a screen can hit', () => {
    const unmapped = API_ERROR_CODES.filter((code) => {
      if (NEVER_SEEN_BY_A_SCREEN.includes(code)) return false
      const message = messageFor(error(code))
      return message === FALLBACK || message.includes('raw server text')
    })
    expect(unmapped).toEqual([])
  })

  it('covers every 409 the ride loop can answer', () => {
    const rideLoop = [
      'VEHICLE_REQUIRED',
      'DEPARTURE_IN_PAST',
      'RIDE_HAS_APPROVED_PASSENGERS',
      'CAPACITY_BELOW_APPROVED',
      'INVALID_STATE_TRANSITION',
      'TOO_EARLY_TO_START',
      'CANNOT_REQUEST_OWN_RIDE',
      'RIDE_NOT_OPEN',
      'NOT_ENOUGH_SEATS',
      'REQUEST_ALREADY_EXISTS',
      'PREVIOUSLY_REJECTED',
      'TOO_LATE_TO_CANCEL',
    ]
    for (const code of rideLoop) {
      expect(messageFor(error(code)), code).not.toBe(FALLBACK)
    }
  })

  it('still answers something for a code this build has never seen', () => {
    expect(messageFor(error('SOME_FUTURE_CODE'))).toBe('raw server text nobody should read')
    expect(messageFor(new Error('boom'))).toBe(FALLBACK)
  })

  it('matches a field error whether or not the backend prefixes it with body.', () => {
    const validation = new ApiError(422, {
      code: 'VALIDATION_ERROR',
      message: 'Request failed validation.',
      details: [{ field: 'body.departure_time', message: 'Must be in the future.' }],
    })
    expect(validation.fieldError('departure_time')).toBe('Must be in the future.')
    expect(validation.fieldError('capacity')).toBeUndefined()
  })
})

describe('a 422 detail', () => {
  it('is matched whether or not the backend prefixes it with body.', () => {
    const named = new ApiError(422, {
      code: 'VALIDATION_ERROR',
      message: 'Request failed validation.',
      details: [{ field: 'body.capacity', message: 'Must be at least 1.' }],
    })
    expect(named.fieldError('capacity')).toBe('Must be at least 1.')
    expect(named.fieldError('price_per_seat')).toBeUndefined()
  })

  it('stays readable when it names the whole body and no single field', () => {
    // PATCH /rides/{id} answered `field: "body"` until the backend fixed it at
    // 0.4.3. `details` is exposed raw so a form can still show the reason — see
    // RideForm's serverErrors(), which buckets anything it cannot place.
    const vague = new ApiError(422, {
      code: 'VALIDATION_ERROR',
      message: 'Request failed validation.',
      details: [{ field: 'body', message: 'notes is the only field that may be null.' }],
    })
    expect(vague.fieldError('notes')).toBeUndefined()
    expect(vague.details).toHaveLength(1)
  })
})
