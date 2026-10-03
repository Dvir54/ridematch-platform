import { describe, expect, it } from 'vitest'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { db, seedOnboardedDriver, seedOnboardedMe, seedRating, seedRequest, seedRide } from './db'

/**
 * The mock API only earns its keep if it refuses what the real backend refuses.
 * These pin the rules that have already drifted once.
 */
describe('mock API matches the contract', () => {
  it('ignores a phone key, which the contract no longer has (D22)', async () => {
    const me = await api.post('/users/me/onboarding', {
      name: 'Dvir Levi',
      phone: '555@0101234',
      date_of_birth: '1996-02-11',
      accepted_terms: true,
    })
    expect(me).not.toHaveProperty('phone')
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

  it('refuses a rating before the ride is completed, and a duplicate after', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'in_progress' })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })

    const early = (await api
      .post('/ratings', { ride_id: ride.id, to_user_id: 3, score: 5 })
      .catch((caught: unknown) => caught)) as ApiError
    expect(early.code).toBe('RIDE_NOT_COMPLETED')

    ride.status = 'completed'
    await api.post('/ratings', { ride_id: ride.id, to_user_id: 3, score: 5 })

    const duplicate = (await api
      .post('/ratings', { ride_id: ride.id, to_user_id: 3, score: 4 })
      .catch((caught: unknown) => caught)) as ApiError
    expect(duplicate.code).toBe('ALREADY_RATED')
  })

  it('updates the cached average on the person just rated', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })
    seedRating({ ride_id: 50, from_user_id: me.id, to_user_id: 3, role_rated: 'passenger', score: 4 })
    db.users.find((u) => u.id === 3)!.passenger_rating = 4
    db.users.find((u) => u.id === 3)!.passenger_rating_count = 1

    await api.post('/ratings', { ride_id: ride.id, to_user_id: 3, score: 5 })

    const passenger = db.users.find((u) => u.id === 3)
    expect(passenger?.passenger_rating_count).toBe(2)
    expect(passenger?.passenger_rating).toBe(4.5)
  })

  it('counts stats across both roles', async () => {
    const me = seedOnboardedDriver()
    const mine = seedRide({ driver_id: me.id, status: 'completed' })
    seedRide({ driver_id: me.id, status: 'upcoming' })
    const someoneElsesRide = seedRide({ driver_id: 2, status: 'completed' })
    seedRequest({ ride_id: someoneElsesRide.id, passenger_id: me.id, status: 'approved' })
    seedRequest({ ride_id: mine.id, passenger_id: 3, status: 'approved' })

    const stats = await api.get('/users/me/stats')
    expect(stats).toMatchObject({
      as_driver: { rides_offered: 2, rides_completed: 1, upcoming_rides: 1, passengers_carried: 1 },
      as_passenger: { trips_requested: 1, trips_completed: 1, upcoming_trips: 0 },
    })
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

/**
 * Order and precedence, as @tests pinned them on the real backend. A mock that
 * answers a different code for the same request is worse than no mock: the screen
 * would be built against a message the user never sees.
 *
 * Each case below is also pinned on the backend side, so a change to either order
 * turns both suites red instead of letting them drift apart quietly:
 *   tests/api/test_requests.py::TestTheOrderOfRefusals
 *   tests/api/test_request_lifecycle.py::TestRideStateBlocksResponses
 *     ::test_an_approved_seat_on_a_started_ride_cannot_be_cancelled
 */
describe('mock API refuses in the same order the backend does', () => {
  const conflict = async (call: Promise<unknown>) =>
    ((await call.catch((caught: unknown) => caught)) as ApiError).code

  it('answers NOT_ENOUGH_SEATS, not REQUEST_ALREADY_EXISTS, when both are true', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 2, available_seats: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'pending' })

    expect(await conflict(api.post(`/rides/${ride.id}/requests`, { seats_requested: 3 }))).toBe(
      'NOT_ENOUGH_SEATS',
    )
  })

  it('answers RIDE_NOT_OPEN, not NOT_ENOUGH_SEATS, on a full ride', async () => {
    seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 1, available_seats: 0, status: 'full' })

    expect(await conflict(api.post(`/rides/${ride.id}/requests`, { seats_requested: 1 }))).toBe(
      'RIDE_NOT_OPEN',
    )
  })

  it('answers INVALID_STATE_TRANSITION once the ride has started, hour or no hour', async () => {
    const me = seedOnboardedMe()
    // in_progress is reachable from departure − 2h, so there is an hour in which the
    // ride has left but the one-hour cancel cutoff has not passed yet (D19).
    const ride = seedRide({
      driver_id: 2,
      status: 'in_progress',
      departure_time: new Date(Date.now() + 90 * 60_000).toISOString(),
    })
    const seat = seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })

    expect(await conflict(api.post(`/requests/${seat.id}/cancel`))).toBe(
      'INVALID_STATE_TRANSITION',
    )
  })

  it('still answers TOO_LATE_TO_CANCEL inside the hour on a ride that has not started', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({
      driver_id: 2,
      departure_time: new Date(Date.now() + 30 * 60_000).toISOString(),
    })
    const seat = seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })

    expect(await conflict(api.post(`/requests/${seat.id}/cancel`))).toBe('TOO_LATE_TO_CANCEL')
  })
})
