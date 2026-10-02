import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { db, seedOnboardedMe, seedRequest } from '../../mocks/db'
import { isoToDateTimeLocal } from '../../lib/dates'
import { renderAsUser } from '../../test/utils'
import { SearchScreen } from './SearchScreen'

function renderScreen() {
  const me = seedOnboardedMe()
  const view = renderAsUser(
    me,
    <Routes>
      <Route path="/app/passenger/search" element={<SearchScreen />} />
      <Route path="/app/passenger/rides/:rideId" element={<p>The ride</p>} />
    </Routes>,
    { route: '/app/passenger/search' },
  )
  return { me, ...view }
}

/** Typing into a place field and taking one of the suggestions Mapbox offers. */
async function pickAddress(
  user: ReturnType<typeof userEvent.setup>,
  label: RegExp,
  text: string,
  index = 0,
) {
  const field = screen.getByRole('combobox', { name: label })
  await user.type(field, text)

  const options = await screen.findByRole('listbox', {
    name: new RegExp(label.source + ' suggestions'),
  })
  const found = (await waitFor(() => options.querySelectorAll('[role="option"]')))[index]
  await user.click(found)
}

/** The seed ride (101): Rothschild 1, Tel Aviv-Yafo → Jaffa 97, Jerusalem, driven by Noa Berman. */
async function searchForSeedRide(user: ReturnType<typeof userEvent.setup>) {
  const seeded = db.rides.find((row) => row.id === 101)!
  await pickAddress(user, /Pickup point/, 'Rothschild 1', 0)
  await pickAddress(user, /Destination/, 'Jaffa 97', 1)
  const departure = screen.getByLabelText(/Departure/)
  await user.clear(departure)
  await user.type(departure, isoToDateTimeLocal(seeded.departure_time))
  await user.click(screen.getByRole('button', { name: 'Search' }))
  return seeded
}

describe('searching for a ride', () => {
  it('finds a ride on the route and shows its match score', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await searchForSeedRide(user)

    expect(await screen.findByText(/% match/)).toBeVisible()
    expect(screen.getByText('Noa Berman driving')).toBeVisible()
  })

  it('will not search until both an address and a time are given', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Choose a pickup point from the suggestions.')).toBeVisible()
    expect(screen.getByText('Choose a destination from the suggestions.')).toBeVisible()
    expect(screen.queryByRole('group', { name: 'Sort results' })).not.toBeInTheDocument()
  })

  it('excludes a ride the passenger already has an active request on', async () => {
    const user = userEvent.setup({ delay: null })
    const { me } = renderScreen()
    seedRequest({ ride_id: 101, passenger_id: me.id, status: 'pending' })

    await searchForSeedRide(user)

    expect(await screen.findByText('Nothing matches yet')).toBeVisible()
  })

  it('still shows a ride the driver already turned down, marked declined (D20)', async () => {
    const user = userEvent.setup({ delay: null })
    const { me } = renderScreen()
    seedRequest({ ride_id: 101, passenger_id: me.id, status: 'rejected' })

    await searchForSeedRide(user)

    expect(await screen.findByText(/% match/)).toBeVisible()
    expect(screen.getByText('Declined')).toBeVisible()
  })

  it('opens the ride behind a result', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await searchForSeedRide(user)
    await user.click(await screen.findByRole('link'))

    expect(await screen.findByText('The ride')).toBeVisible()
  })
})
