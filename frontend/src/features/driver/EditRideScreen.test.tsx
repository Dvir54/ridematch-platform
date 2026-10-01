import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedDriver, seedRequest, seedRide } from '../../mocks/db'
import { server } from '../../mocks/node'
import { renderAsUser } from '../../test/utils'
import { EditRideScreen } from './EditRideScreen'

/**
 * Contract 0.4.2 decided that a location field or `departure_time` counts as a
 * change by **presence**, even when the value is identical — so on a ride with
 * an approved passenger, a form that posts everything would always 409. These
 * tests watch the wire, not just the result.
 */
const patches: Record<string, unknown>[] = []

server.events.on('request:start', ({ request }) => {
  if (request.method !== 'PATCH' || !request.url.includes('/rides/')) return
  void request
    .clone()
    .json()
    .then((body) => patches.push(body as Record<string, unknown>))
})

afterEach(() => {
  patches.length = 0
})

function renderScreen(me: UserMe, rideId: number) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/driver/rides/:rideId/edit" element={<EditRideScreen />} />
      <Route path="/app/driver/rides/:rideId" element={<p>Back on the ride</p>} />
      <Route path="/app/passenger/rides/:rideId" element={<p>Passenger view</p>} />
    </Routes>,
    { route: `/app/driver/rides/${rideId}/edit` },
  )
}

describe('editing a ride with no approved passengers', () => {
  it('sends only the fields that actually changed', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, price_per_seat: '18.00' })
    renderScreen(me, ride.id)

    const price = await screen.findByLabelText(/Price per seat/)
    await user.clear(price)
    await user.type(price, '22')
    await user.click(screen.getByRole('button', { name: 'Save the changes' }))

    expect(await screen.findByText('Back on the ride')).toBeVisible()
    expect(patches).toEqual([{ price_per_seat: '22.00' }])
    expect(db.rides.find((row) => row.id === ride.id)?.price_per_seat).toBe('22.00')
  })

  it('still offers the route and the time while the seats are all free', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    renderScreen(me, ride.id)

    expect(await screen.findByRole('combobox', { name: /Pickup point/ })).toBeVisible()
    expect(screen.getByLabelText(/Departure/)).toBeVisible()
  })

  it('sends only the preference that was toggled, because PATCH merges (D16)', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({
      driver_id: me.id,
      preferences: { smoking: false, pets: false, music: true, gender_only: false },
    })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('switch', { name: 'Pets allowed' }))
    await user.click(screen.getByRole('button', { name: 'Save the changes' }))

    await screen.findByText('Back on the ride')
    expect(patches).toEqual([{ preferences: { pets: true } }])
    // The keys left alone keep their old values.
    expect(db.rides.find((row) => row.id === ride.id)?.preferences).toEqual({
      smoking: false,
      pets: true,
      music: true,
      gender_only: false,
    })
  })
})

describe('editing a ride that already carries a passenger', () => {
  function seedRideWithPassenger() {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, capacity: 3, available_seats: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved', seats_requested: 1 })
    return { me, ride }
  }

  it('shows the route and time as settled rather than as fields', async () => {
    const { me, ride } = seedRideWithPassenger()
    renderScreen(me, ride.id)

    expect(await screen.findByText('Route and time are set')).toBeVisible()
    expect(screen.queryByRole('combobox', { name: /Pickup point/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Departure/)).not.toBeInTheDocument()
  })

  it('saves a price change without touching the locked fields', async () => {
    const user = userEvent.setup()
    const { me, ride } = seedRideWithPassenger()
    renderScreen(me, ride.id)

    const price = await screen.findByLabelText(/Price per seat/)
    await user.clear(price)
    await user.type(price, '30')
    await user.click(screen.getByRole('button', { name: 'Save the changes' }))

    expect(await screen.findByText('Back on the ride')).toBeVisible()
    // No location key and no departure_time, so no RIDE_HAS_APPROVED_PASSENGERS.
    expect(patches).toEqual([{ price_per_seat: '30.00' }])
  })

  it('refuses a capacity below the seats already approved', async () => {
    const user = userEvent.setup()
    const { me, ride } = seedRideWithPassenger()
    renderScreen(me, ride.id)

    await user.selectOptions(await screen.findByLabelText(/Seats for passengers/), '1')
    expect(screen.getByText(/1 already approved/)).toBeVisible()

    // 1 seat is still fine — one passenger holds one seat.
    await user.selectOptions(screen.getByLabelText(/Seats for passengers/), '1')
    await user.click(screen.getByRole('button', { name: 'Save the changes' }))
    await screen.findByText('Back on the ride')
    expect(patches).toEqual([{ capacity: 1 }])
    // Dropping to one seat fills the ride, since that one seat is taken.
    expect(db.rides.find((row) => row.id === ride.id)?.status).toBe('full')
  })
})

describe('reaching the edit form for a ride that is not yours', () => {
  it('sends you to the passenger view instead', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: 2 })
    renderScreen(me, ride.id)

    expect(await screen.findByText('Passenger view')).toBeVisible()
  })

  it('explains that a cancelled ride can no longer be edited', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'cancelled' })
    renderScreen(me, ride.id)

    expect(await screen.findByText('This ride is cancelled')).toBeVisible()
  })
})
