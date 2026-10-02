import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedMe, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { MyTripsScreen } from './MyTripsScreen'

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

function renderScreen(me: UserMe) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/passenger/trips" element={<MyTripsScreen />} />
      <Route path="/app/passenger/rides/:rideId" element={<p>The ride</p>} />
    </Routes>,
    { route: '/app/passenger/trips' },
  )
}

describe('My trips', () => {
  it('opens on the active trips and says who is driving', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, seats_requested: 2 })
    renderScreen(me)

    expect(await screen.findByText('Waiting on the driver')).toBeVisible()
    expect(screen.getByText(/2 seats · Noa Berman driving/)).toBeVisible()
  })

  it('keeps closed requests out of Active and finds them under Past', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'rejected' })
    renderScreen(me)

    expect(await screen.findByText('No trips yet')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Past' }))
    expect(await screen.findByText('Declined')).toBeVisible()
  })

  it('withdraws a pending request from the list', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    const request = seedRequest({ ride_id: ride.id, passenger_id: me.id })
    renderScreen(me)

    await user.click(await screen.findByRole('button', { name: 'Withdraw the request' }))
    await user.click(screen.getByRole('button', { name: 'Withdraw it' }))

    // Cancelled is not an Active status, so the row leaves this list.
    expect(await screen.findByText('No trips yet')).toBeVisible()
    expect(db.requests.find((row) => row.id === request.id)?.status).toBe('cancelled')
  })

  it('explains the lock rather than offering a cancel that would 409', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, departure_time: hoursFromNow(0.5) })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })
    renderScreen(me)

    expect(await screen.findByText(/lock an hour before departure/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Give up the seat' })).not.toBeInTheDocument()
  })

  it('opens the ride behind a trip', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: ride.id, passenger_id: me.id })
    renderScreen(me)

    await user.click(await screen.findByRole('link'))
    expect(await screen.findByText('The ride')).toBeVisible()
  })
})
