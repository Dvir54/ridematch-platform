import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedMe, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { PassengerRideScreen } from './PassengerRideScreen'

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

function renderScreen(me: UserMe, rideId: number) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/passenger/rides/:rideId" element={<PassengerRideScreen />} />
      <Route path="/app/driver/rides/:rideId" element={<p>Driver view</p>} />
      <Route path="/app/passenger/trips" element={<p>My trips</p>} />
    </Routes>,
    { route: `/app/passenger/rides/${rideId}` },
  )
}

describe('asking for a seat', () => {
  it('creates a pending request and then shows its state instead of the button', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 3, available_seats: 3 })
    renderScreen(me, ride.id)

    await user.selectOptions(await screen.findByLabelText(/How many seats/), '2')
    await user.click(screen.getByRole('button', { name: 'Ask for a seat' }))

    expect(await screen.findByText('Waiting on the driver')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Ask for a seat' })).not.toBeInTheDocument()

    const created = db.requests.find((row) => row.passenger_id === me.id)
    expect(created?.seats_requested).toBe(2)
    expect(created?.status).toBe('pending')
  })

  it('shows the total for the seats asked for', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 3, available_seats: 3, price_per_seat: '25.00' })
    renderScreen(me, ride.id)

    expect(await screen.findByText(/₪25.00 in total/)).toBeVisible()
    await user.selectOptions(screen.getByLabelText(/How many seats/), '3')
    expect(screen.getByText(/₪75.00 in total/)).toBeVisible()
  })

  it('offers no more seats than the ride has free', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 4, available_seats: 2 })
    renderScreen(me, ride.id)

    const select = await screen.findByLabelText(/How many seats/)
    expect(select.querySelectorAll('option')).toHaveLength(2)
  })

  it('says a ride that is no longer upcoming is not taking requests', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, status: 'in_progress' })
    renderScreen(me, ride.id)

    expect(await screen.findByText(/This ride is in_progress, so it is not taking requests/)).toBeVisible()
  })

  it('stops offering the button once the driver has refused this ride', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 3, available_seats: 3 })
    // A rejection is final for this ride (D2), so the screen has to know about it
    // rather than offer a button whose only answer is PREVIOUSLY_REJECTED.
    db.requests.push({
      id: db.nextRequestId++,
      ride_id: ride.id,
      passenger_id: me.id,
      seats_requested: 1,
      status: 'rejected',
      requested_at: hoursFromNow(-3),
      responded_at: hoursFromNow(-2),
    })
    renderScreen(me, ride.id)

    expect(await screen.findByText('Declined')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Ask for a seat' })).not.toBeInTheDocument()
    expect(screen.getByText(/final for this ride/)).toBeVisible()
  })
})

describe('giving a seat back', () => {
  it('withdraws a pending request', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    const request = seedRequest({ ride_id: ride.id, passenger_id: me.id })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('button', { name: 'Withdraw the request' }))
    await user.click(screen.getByRole('button', { name: 'Withdraw it' }))

    // Your own cancel is not final: the screen offers the seat again (D2).
    expect(await screen.findByRole('button', { name: 'Ask for a seat' })).toBeVisible()
    expect(db.requests.find((row) => row.id === request.id)?.status).toBe('cancelled')
  })

  it('gives an approved seat back and frees it on the ride', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({
      driver_id: 2,
      capacity: 1,
      available_seats: 0,
      status: 'full',
      departure_time: hoursFromNow(6),
    })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('button', { name: 'Give up the seat' }))
    await user.click(screen.getByRole('button', { name: 'Give up the seat' }))

    expect(await screen.findByRole('button', { name: 'Ask for a seat' })).toBeVisible()
    const after = db.rides.find((row) => row.id === ride.id)
    expect(after?.available_seats).toBe(1)
    // A full ride opens up again when a seat comes back (CONTRACT §3).
    expect(after?.status).toBe('upcoming')
  })

  it('explains the one-hour lock instead of offering a button that would 409', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, departure_time: hoursFromNow(0.5) })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })
    renderScreen(me, ride.id)

    expect(await screen.findByText(/lock an hour before departure/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Give up the seat' })).not.toBeInTheDocument()
  })
})

describe('the plate', () => {
  it('stays hidden while the request is only pending', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'pending' })
    renderScreen(me, ride.id)

    expect(await screen.findByText(/White Toyota Corolla/)).toBeVisible()
    expect(screen.queryByText(/Plate/)).not.toBeInTheDocument()
  })

  it('appears once the seat is approved (D14)', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, capacity: 3, available_seats: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })
    renderScreen(me, ride.id)

    expect(await screen.findByText('Plate 12-345-67')).toBeVisible()
  })
})

describe('opening your own ride on the passenger route', () => {
  it('redirects to the driver view, where you can act on it', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: me.id })
    renderScreen(me, ride.id)

    expect(await screen.findByText('Driver view')).toBeVisible()
  })
})
