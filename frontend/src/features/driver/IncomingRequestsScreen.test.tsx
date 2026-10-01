import { Route, Routes } from 'react-router-dom'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedDriver, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { IncomingRequestsScreen } from './IncomingRequestsScreen'

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

/** Everything is seeded before the render, so the first fetch sees the whole set. */
function renderScreen(me: UserMe) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/driver/requests" element={<IncomingRequestsScreen />} />
      <Route path="/app/driver/rides/:rideId" element={<p>The ride</p>} />
    </Routes>,
    { route: '/app/driver/requests' },
  )
}

describe('the driver Requests tab', () => {
  it('shows each waiting passenger with the seats they asked for', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    seedRequest({ ride_id: ride.id, passenger_id: 3, seats_requested: 2 })
    renderScreen(me)

    expect(await screen.findByText('Omer Katz')).toBeVisible()
    expect(screen.getByText(/2 seats · asked/)).toBeVisible()
  })

  it('groups the flat list by ride, soonest departure first', async () => {
    const me = seedOnboardedDriver()
    const soon = seedRide({
      driver_id: me.id,
      departure_time: hoursFromNow(4),
      start_address: 'Allenby Street 40, Tel Aviv-Yafo, Israel',
    })
    const later = seedRide({
      driver_id: me.id,
      departure_time: hoursFromNow(30),
      start_address: 'Jaffa Street 97, Jerusalem, Israel',
    })
    seedRequest({ ride_id: later.id, passenger_id: 2 })
    seedRequest({ ride_id: soon.id, passenger_id: 3 })
    renderScreen(me)

    const links = await screen.findAllByRole('link')
    expect(links).toHaveLength(2)
    expect(within(links[0]).getByText(/Allenby Street 40/)).toBeVisible()
    expect(within(links[1]).getByText(/Jaffa Street 97/)).toBeVisible()
  })

  it('approves from the tab and drops the request off the pending list', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, capacity: 2, available_seats: 2 })
    const request = seedRequest({ ride_id: ride.id, passenger_id: 3 })
    renderScreen(me)

    await user.click(await screen.findByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('Nobody is waiting')).toBeVisible()
    expect(db.requests.find((row) => row.id === request.id)?.status).toBe('approved')
    expect(db.rides.find((row) => row.id === ride.id)?.available_seats).toBe(1)
  })

  it('ignores requests on rides that are not yours', async () => {
    const me = seedOnboardedDriver()
    const someoneElse = seedRide({ driver_id: 2 })
    seedRequest({ ride_id: someoneElse.id, passenger_id: 3 })
    renderScreen(me)

    expect(await screen.findByText('Nobody is waiting')).toBeVisible()
  })

  it('leaves requests that were already answered out of the tab', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })
    seedRequest({ ride_id: ride.id, passenger_id: 2, status: 'rejected' })
    renderScreen(me)

    expect(await screen.findByText('Nobody is waiting')).toBeVisible()
  })

  it('links each group to its ride', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id })
    seedRequest({ ride_id: ride.id, passenger_id: 3 })
    renderScreen(me)

    await screen.findByText('Omer Katz')
    await user.click(screen.getByRole('link'))
    expect(await screen.findByText('The ride')).toBeVisible()
  })
})
