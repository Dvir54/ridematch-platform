import { describe, expect, it } from 'vitest'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { seedOnboardedDriver, seedOnboardedMe, seedRequest, seedRide } from './db'

/**
 * The mock API only earns its keep if it refuses what the real backend refuses.
 * These pin the rules that have already drifted once.
 */
describe('mock API matches the contract', () => {
  it('rejects a phone the contract pattern forbids, on onboarding', async () => {
    const error = (await api
      .post('/users/me/onboarding', {
        name: 'Dvir Levi',
        phone: '555@0101234',
        date_of_birth: '1996-02-11',
        accepted_terms: true,
      })
      .catch((caught: unknown) => caught)) as ApiError

    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.fieldError('phone')).toBeDefined()
  })

  it('rejects the same phone on PATCH /users/me', async () => {
    seedOnboardedMe()

    const error = (await api
      .patch('/users/me', { phone: '555@0101234' })
      .catch((caught: unknown) => caught)) as ApiError

    expect(error.status).toBe(422)
    expect(error.fieldError('phone')).toBeDefined()
  })

  it('accepts a well-formed phone and still lets null clear it', async () => {
    seedOnboardedMe()

    await expect(api.patch('/users/me', { phone: '+972 50-123-4567' })).resolves.toMatchObject({
      phone: '+972 50-123-4567',
    })
    // Brackets and dots are valid since 0.4.1, and are stored exactly as typed.
    await expect(api.patch('/users/me', { phone: '+1 (555) 010-9999' })).resolves.toMatchObject({
      phone: '+1 (555) 010-9999',
    })
    await expect(api.patch('/users/me', { phone: null })).resolves.toMatchObject({ phone: null })
  })

  it('requires a real boolean for accepted_terms', async () => {
    const error = (await api
      .post('/users/me/onboarding', {
        name: 'Dvir Levi',
        date_of_birth: '1996-02-11',
        accepted_terms: 'yes',
      })
      .catch((caught: unknown) => caught)) as ApiError

    expect(error.code).toBe('TERMS_NOT_ACCEPTED')
  })
})

describe('preference merging', () => {
  it('keeps the other notification keys when a patch names one', async () => {
    seedOnboardedMe()

    await expect(
      api.patch('/users/me', { preferences: { notifications: { email: false } } }),
    ).resolves.toMatchObject({
      preferences: {
        notifications: { email: false, push: true, websocket: true },
        language: 'en',
        default_mode: null,
      },
    })
  })

  it('fills the notification defaults when onboarding sends a partial sub-object', async () => {
    await expect(
      api.post('/users/me/onboarding', {
        name: 'Dvir Levi',
        date_of_birth: '1996-02-11',
        accepted_terms: true,
        preferences: { notifications: { websocket: false } },
      }),
    ).resolves.toMatchObject({
      preferences: { notifications: { email: true, push: true, websocket: false } },
    })
  })
})

/**
 * The 409s the ride loop turns on. These go through the client rather than a
 * screen, because a screen can only show one of them at a time and the point here
 * is that the mock refuses everything CONTRACT §4 says it must.
 */
describe('mock API refuses what the ride loop forbids', () => {
  const conflict = async (call: Promise<unknown>) =>
    ((await call.catch((caught: unknown) => caught)) as ApiError).code

  it('will not let a driver offer a ride without a car', async () => {
    seedOnboardedMe()
    expect(
      await conflict(
        api.post('/rides', {
          start_lat: 32,
          start_lng: 34,
          start_address: 'A',
          end_lat: 31,
          end_lng: 35,
          end_address: 'B',
          departure_time: new Date(Date.now() + 3_600_000).toISOString(),
          capacity: 2,
          price_per_seat: '10.00',
        }),
      ),
    ).toBe('VEHICLE_REQUIRED')
  })

  it('will not let a driver ask for a seat on their own ride', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    expect(await conflict(api.post(`/rides/${ride.id}/requests`, {}))).toBe(
      'CANNOT_REQUEST_OWN_RIDE',
    )
  })

  it('refuses a second active request on the same ride', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id })
    expect(await conflict(api.post(`/rides/${ride.id}/requests`, {}))).toBe(
      'REQUEST_ALREADY_EXISTS',
    )
  })

  it('refuses more seats than the ride has free', async () => {
    seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 2, available_seats: 2 })
    expect(await conflict(api.post(`/rides/${ride.id}/requests`, { seats_requested: 3 }))).toBe(
      'NOT_ENOUGH_SEATS',
    )
  })

  it('allows a fresh request after the passenger’s own cancel, but not after a reject (D2)', async () => {
    const me = seedOnboardedMe()
    const cancelled = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: cancelled.id, passenger_id: me.id, status: 'cancelled' })
    await expect(api.post(`/rides/${cancelled.id}/requests`, {})).resolves.toMatchObject({
      status: 'pending',
    })

    const rejected = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: rejected.id, passenger_id: me.id, status: 'rejected' })
    expect(await conflict(api.post(`/rides/${rejected.id}/requests`, {}))).toBe(
      'PREVIOUSLY_REJECTED',
    )
  })

  it('hides another driver’s passenger list', async () => {
    seedOnboardedDriver()
    const ride = seedRide({ driver_id: 2 })
    expect(await conflict(api.get(`/rides/${ride.id}/requests`))).toBe('FORBIDDEN')
  })

  it('will not let someone else edit or cancel a ride', async () => {
    seedOnboardedDriver()
    const ride = seedRide({ driver_id: 2 })
    expect(await conflict(api.patch(`/rides/${ride.id}`, { price_per_seat: '1.00' }))).toBe(
      'FORBIDDEN',
    )
    expect(await conflict(api.post(`/rides/${ride.id}/cancel`))).toBe('FORBIDDEN')
  })

  it('treats a departure_time of the same value as a change (contract 0.4.2)', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, capacity: 2, available_seats: 1 })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })

    expect(
      await conflict(api.patch(`/rides/${ride.id}`, { departure_time: ride.departure_time })),
    ).toBe('RIDE_HAS_APPROVED_PASSENGERS')
    // Price is always editable, passengers or not.
    await expect(api.patch(`/rides/${ride.id}`, { price_per_seat: '31.00' })).resolves.toMatchObject(
      { price_per_seat: '31.00' },
    )
  })
})
