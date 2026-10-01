import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { seedOnboardedDriver, seedOnboardedMe, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { MyRidesScreen } from './MyRidesScreen'

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

function renderScreen(me: UserMe) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/driver/rides" element={<MyRidesScreen />} />
      <Route path="/app/driver/rides/new" element={<p>New ride form</p>} />
      <Route path="/app/driver/rides/:rideId" element={<p>The ride</p>} />
      <Route path="/app/profile" element={<p>Profile</p>} />
    </Routes>,
    { route: '/app/driver/rides' },
  )
}

describe('My rides', () => {
  it('lists the planned rides in departure order', async () => {
    const me = seedOnboardedDriver()
    seedRide({
      driver_id: me.id,
      departure_time: hoursFromNow(30),
      start_address: 'Jaffa Street 97, Jerusalem, Israel',
    })
    seedRide({
      driver_id: me.id,
      departure_time: hoursFromNow(4),
      start_address: 'Allenby Street 40, Tel Aviv-Yafo, Israel',
    })
    renderScreen(me)

    // "Offer a ride" is a link and renders at once, so wait for a card first.
    await screen.findByText(/Allenby Street 40/)
    const rides = screen
      .getAllByRole('link')
      .filter((link) => link.textContent?.includes('seats free'))
    expect(rides).toHaveLength(2)
    expect(rides[0].textContent).toContain('Allenby Street 40')
    expect(rides[1].textContent).toContain('Jaffa Street 97')
  })

  it('keeps finished rides out of Planned and finds them under Finished', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    seedRide({ driver_id: me.id, status: 'completed' })
    renderScreen(me)

    expect(await screen.findByText('No rides here')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Finished' }))
    expect(await screen.findByText('Completed')).toBeVisible()
  })

  it('shows another driver’s rides to nobody but them', async () => {
    const me = seedOnboardedDriver()
    seedRide({ driver_id: 2 })
    renderScreen(me)

    expect(await screen.findByText('No rides here')).toBeVisible()
  })

  it('asks for a car instead of offering the form when the profile has none', async () => {
    const me = seedOnboardedMe()
    renderScreen(me)

    expect(await screen.findByText('Add your car first')).toBeVisible()
    expect(screen.queryByRole('link', { name: 'Offer a ride' })).not.toBeInTheDocument()
  })

  it('opens the create form from the primary action', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    renderScreen(me)

    await user.click(await screen.findByRole('link', { name: 'Offer a ride' }))
    expect(await screen.findByText('New ride form')).toBeVisible()
  })
})
