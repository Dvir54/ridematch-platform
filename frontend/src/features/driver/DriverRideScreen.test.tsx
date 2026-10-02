import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedDriver, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { DriverRideScreen } from './DriverRideScreen'

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

function renderScreen(me: UserMe, rideId: number) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/driver/rides/:rideId" element={<DriverRideScreen />} />
      <Route path="/app/driver/rides/:rideId/edit" element={<p>Edit form</p>} />
      <Route path="/app/driver/rides" element={<p>My rides</p>} />
      <Route path="/app/passenger/rides/:rideId" element={<p>Passenger view</p>} />
    </Routes>,
    { route: `/app/driver/rides/${rideId}` },
  )
}

describe('answering requests on your own ride', () => {
  it('approves a seat, moves the count and fills the ride', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, capacity: 1, available_seats: 1 })
    seedRequest({ ride_id: ride.id, passenger_id: 3, seats_requested: 1 })
    renderScreen(me, ride.id)

    expect(await screen.findByText(/1 of 1 seats free/)).toBeVisible()
    await user.click(await screen.findByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('Seat confirmed')).toBeVisible()
    // available_seats hit zero, so the ride is full (CONTRACT §3).
    expect(await screen.findByText(/No seats left of 1/)).toBeVisible()
    expect(screen.getByText('Full')).toBeVisible()
    expect(db.rides.find((row) => row.id === ride.id)?.status).toBe('full')
  })

  it('explains NOT_ENOUGH_SEATS when the last seat went while the list was open', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, capacity: 1, available_seats: 1 })
    seedRequest({ ride_id: ride.id, passenger_id: 3, seats_requested: 1 })
    renderScreen(me, ride.id)

    await screen.findByRole('button', { name: 'Approve' })
    // Somebody else's approval lands between the render and the click.
    seedRequest({ ride_id: ride.id, passenger_id: 2, seats_requested: 1, status: 'approved' })
    db.rides.find((row) => row.id === ride.id)!.available_seats = 0

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText("There aren't that many seats left.")).toBeVisible()
  })

  it('warns that declining is final before it does it', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    const request = seedRequest({ ride_id: ride.id, passenger_id: 3 })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('button', { name: 'Decline' }))
    expect(screen.getByText(/final for this ride/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Decline the seat' }))
    expect(await screen.findByText('Declined')).toBeVisible()
    expect(db.requests.find((row) => row.id === request.id)?.status).toBe('rejected')
  })
})

describe('the driver actions a ride status allows', () => {
  it('keeps Start disabled until two hours before departure', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, departure_time: hoursFromNow(5) })
    renderScreen(me, ride.id)

    expect(await screen.findByRole('button', { name: 'Start the ride' })).toBeDisabled()
    expect(screen.getByText(/two hours before departure/)).toBeVisible()
  })

  it('starts a ride inside the window and declines whoever was still waiting', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, departure_time: hoursFromNow(1) })
    const waiting = seedRequest({ ride_id: ride.id, passenger_id: 3 })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('button', { name: 'Start the ride' }))

    expect(await screen.findByText('On the road')).toBeVisible()
    expect(db.requests.find((row) => row.id === waiting.id)?.status).toBe('rejected')
    expect(screen.getByRole('button', { name: 'Finish the ride' })).toBeVisible()
  })

  it('completes a ride that is under way', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'in_progress' })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('button', { name: 'Finish the ride' }))

    expect(await screen.findByText('Completed')).toBeVisible()
    expect(db.rides.find((row) => row.id === ride.id)?.status).toBe('completed')
  })

  it('cancels a ride only after asking, and cancels the requests with it', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, capacity: 3, available_seats: 2 })
    const aboard = seedRequest({
      ride_id: ride.id,
      passenger_id: 3,
      status: 'approved',
      seats_requested: 1,
    })
    renderScreen(me, ride.id)

    await user.click(await screen.findByRole('button', { name: 'Cancel the ride' }))
    expect(screen.getByText(/will be told the ride is off/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Cancel the ride' }))

    expect(await screen.findByText(/Nothing left to do here/)).toBeVisible()
    expect(db.rides.find((row) => row.id === ride.id)?.status).toBe('cancelled')
    // The approved seat goes with it (CONTRACT §3), and the passenger is told.
    expect(db.requests.find((row) => row.id === aboard.id)?.status).toBe('cancelled')
  })

  it('offers nothing to do on a completed ride', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'completed' })
    renderScreen(me, ride.id)

    expect(await screen.findByText(/This ride is completed/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Start the ride' })).not.toBeInTheDocument()
  })
})

describe('the plate', () => {
  it('is shown to the driver on their own ride', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    renderScreen(me, ride.id)

    expect(await screen.findByText('Plate 88-123-45')).toBeVisible()
  })
})

describe('opening someone else’s ride on the driver route', () => {
  it('redirects to the passenger view', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: 2 })
    renderScreen(me, ride.id)

    expect(await screen.findByText('Passenger view')).toBeVisible()
  })

  it('says so plainly when the ride does not exist', async () => {
    const me = seedOnboardedDriver()
    renderScreen(me, 9999)

    expect(await screen.findByText("That's gone — it may have been cancelled or deleted.")).toBeVisible()
  })
})
