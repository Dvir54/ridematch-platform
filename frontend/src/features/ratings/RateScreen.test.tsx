import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedDriver, seedRating, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { RateScreen } from './RateScreen'

function renderScreen(me: UserMe, route: string) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/rate/:rideId/:userId" element={<RateScreen />} />
      <Route path="/app/driver" element={<p>Driver home</p>} />
    </Routes>,
    { route },
  )
}

describe('rating someone after a ride', () => {
  it('sends a score, tags and comment, then returns home', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })
    renderScreen(me, `/app/rate/${ride.id}/3`)

    expect(await screen.findByText('Rate Omer Katz')).toBeVisible()
    expect(screen.getByText('As your passenger on this ride.')).toBeVisible()

    await user.click(screen.getByLabelText('5'))
    await user.click(screen.getByRole('button', { name: 'friendly' }))
    await user.type(screen.getByLabelText(/Anything else/), 'Great ride')
    await user.click(screen.getByRole('button', { name: 'Send rating' }))

    expect(await screen.findByText('Driver home')).toBeVisible()
    const saved = db.ratings.find((row) => row.ride_id === ride.id && row.to_user_id === 3)
    expect(saved).toMatchObject({
      from_user_id: me.id,
      role_rated: 'passenger',
      score: 5,
      comment: 'Great ride',
      tags: ['friendly'],
    })
  })

  it('refuses to submit with no score picked', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })
    renderScreen(me, `/app/rate/${ride.id}/3`)

    await screen.findByText('Rate Omer Katz')
    await user.click(screen.getByRole('button', { name: 'Send rating' }))

    expect(await screen.findByText('Pick a score from 1 to 5.')).toBeVisible()
    expect(db.ratings).toHaveLength(0)
  })

  it('shows the server message when this person was already rated', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })
    seedRating({ ride_id: ride.id, from_user_id: me.id, to_user_id: 3, role_rated: 'passenger' })
    renderScreen(me, `/app/rate/${ride.id}/3`)

    await screen.findByText('Rate Omer Katz')
    await user.click(screen.getByLabelText('4'))
    await user.click(screen.getByRole('button', { name: 'Send rating' }))

    expect(await screen.findByText('You already rated this person for this ride.')).toBeVisible()
  })
})
