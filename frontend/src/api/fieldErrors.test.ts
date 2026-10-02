import { describe, expect, it } from 'vitest'
import { ApiError } from './errors'
import { collectFieldErrors } from './fieldErrors'

const OWNERS = {
  start_lat: 'start',
  start_lng: 'start',
  start_address: 'start',
  capacity: 'capacity',
  'vehicle.plate': 'plate',
} as const

const validation = (details: { field: string; message: string }[]) =>
  new ApiError(422, { code: 'VALIDATION_ERROR', message: 'Request failed validation.', details })

describe('collectFieldErrors', () => {
  it('places a field whether or not the server prefixed it with body.', () => {
    const { fields } = collectFieldErrors(
      validation([
        { field: 'body.capacity', message: 'Too many.' },
        { field: 'vehicle.plate', message: 'Too short.' },
      ]),
      OWNERS,
    )
    expect(fields).toEqual({ capacity: 'Too many.', plate: 'Too short.' })
  })

  it('routes several server fields to the one control that owns them', () => {
    const { fields, rest } = collectFieldErrors(
      validation([{ field: 'body.start_lat', message: 'Not on land.' }]),
      OWNERS,
    )
    expect(fields.start).toBe('Not on land.')
    expect(rest).toEqual([])
  })

  it('keeps the first message when two details name the same control', () => {
    // The more specific complaint arrives first; overwriting it with a vaguer one
    // about the same input loses information.
    const { fields } = collectFieldErrors(
      validation([
        { field: 'body.start_lat', message: 'Not on land.' },
        { field: 'body.start_address', message: 'Required.' },
      ]),
      OWNERS,
    )
    expect(fields.start).toBe('Not on land.')
  })

  it('hands back anything it cannot place, so no reason is dropped', () => {
    // Contract 0.4.5: `field` may get more specific in a later version, so a form
    // must always have somewhere to put a name it does not recognise.
    const { fields, rest } = collectFieldErrors(
      validation([
        { field: 'body', message: 'notes is the only field that may be null.' },
        { field: 'body.preferences.pets', message: 'Must be a boolean.' },
      ]),
      OWNERS,
    )
    expect(fields).toEqual({})
    expect(rest).toEqual([
      'notes is the only field that may be null.',
      'Must be a boolean.',
    ])
  })

  it('is empty for an error that is not an ApiError, and for one with no details', () => {
    expect(collectFieldErrors(new Error('boom'), OWNERS)).toEqual({ fields: {}, rest: [] })
    expect(
      collectFieldErrors(new ApiError(409, { code: 'RIDE_NOT_OPEN', message: 'Closed.' }), OWNERS),
    ).toEqual({ fields: {}, rest: [] })
  })
})
