import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { db, seedOnboardedDriver, seedOnboardedMe } from '../../mocks/db'
import { isoToDateTimeLocal } from '../../lib/dates'
import { renderAsUser } from '../../test/utils'
import { CreateRideScreen } from './CreateRideScreen'

const departure = new Date(Date.now() + 36 * 3_600_000)

function renderScreen(me = seedOnboardedDriver()) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/driver/rides/new" element={<CreateRideScreen />} />
      <Route path="/app/driver/rides/:rideId" element={<p>Ride posted</p>} />
      <Route path="/app/profile" element={<p>Profile</p>} />
    </Routes>,
    { route: '/app/driver/rides/new' },
  )
}

/** Typing into a place field and taking the first suggestion Mapbox offers. */
async function pickAddress(user: ReturnType<typeof userEvent.setup>, label: RegExp, text: string) {
  const field = screen.getByRole('combobox', { name: label })
  await user.type(field, text)

  const options = await screen.findByRole('listbox', { name: new RegExp(label.source + ' suggestions') })
  const first = (await waitFor(() => options.querySelectorAll('[role="option"]')))[0]
  await user.click(first)
}

describe('offering a ride', () => {
  it('sends the address Mapbox resolved together with its coordinates', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await pickAddress(user, /Pickup point/, 'Rothschild 1')
    await pickAddress(user, /Destination/, 'Jaffa 97')

    await user.type(screen.getByLabelText(/Departure/), isoToDateTimeLocal(departure.toISOString()))
    await user.type(screen.getByLabelText(/Price per seat/), '25.5')
    await user.selectOptions(screen.getByLabelText(/Seats for passengers/), '2')

    await user.click(screen.getByRole('button', { name: 'Post the ride' }))

    expect(await screen.findByText('Ride posted')).toBeVisible()

    const ride = db.rides.find((row) => row.driver_id === 1)
    expect(ride).toBeDefined()
    expect(ride?.start_address).toBe('Rothschild 1, Tel Aviv-Yafo, Israel')
    expect(ride?.start_lat).toBeCloseTo(32.0853)
    expect(ride?.start_lng).toBeCloseTo(34.7818)
    expect(ride?.end_address).toBe('Jaffa 97, Tel Aviv-Yafo, Israel')
    // Money crosses the wire as a two-place string, never a float (CONTRACT §2).
    expect(ride?.price_per_seat).toBe('25.50')
    expect(ride?.capacity).toBe(2)
    expect(ride?.available_seats).toBe(2)
    expect(ride?.status).toBe('upcoming')
  })

  it('fills every ride preference on create, even the ones left untouched', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await pickAddress(user, /Pickup point/, 'Dizengoff 50')
    await pickAddress(user, /Destination/, 'Herzl 12')
    await user.type(screen.getByLabelText(/Departure/), isoToDateTimeLocal(departure.toISOString()))
    await user.type(screen.getByLabelText(/Price per seat/), '18')
    await user.click(screen.getByRole('switch', { name: 'Pets allowed' }))
    await user.click(screen.getByRole('button', { name: 'Post the ride' }))

    await screen.findByText('Ride posted')
    const ride = db.rides.find((row) => row.driver_id === 1)
    expect(ride?.preferences).toEqual({
      smoking: false,
      pets: true,
      music: true,
      gender_only: false,
    })
  })

  it('will not post a ride whose address was typed but never chosen', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await user.type(screen.getByRole('combobox', { name: /Pickup point/ }), 'Somewhere vague')
    await user.type(screen.getByLabelText(/Price per seat/), '20')
    await user.click(screen.getByRole('button', { name: 'Post the ride' }))

    expect(
      await screen.findByText('Choose a pickup point from the suggestions.'),
    ).toBeVisible()
    expect(screen.getByText('Choose a destination from the suggestions.')).toBeVisible()
    expect(db.rides.some((row) => row.driver_id === 1)).toBe(false)
  })

  it('rejects a price the Money pattern would not accept', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await pickAddress(user, /Pickup point/, 'Dizengoff 50')
    await pickAddress(user, /Destination/, 'Herzl 12')
    await user.type(screen.getByLabelText(/Departure/), isoToDateTimeLocal(departure.toISOString()))
    await user.type(screen.getByLabelText(/Price per seat/), '25.505')
    await user.click(screen.getByRole('button', { name: 'Post the ride' }))

    expect(await screen.findByText(/up to two decimals/)).toBeVisible()
    expect(db.rides.some((row) => row.driver_id === 1)).toBe(false)
  })

  it('asks for a car instead of a form when the profile has none', async () => {
    renderScreen(seedOnboardedMe())

    expect(await screen.findByText('Add your car first')).toBeVisible()
    expect(screen.queryByRole('combobox', { name: /Pickup point/ })).not.toBeInTheDocument()
  })

  it('warns that a gender-only ride nobody can match is pointless', async () => {
    const user = userEvent.setup({ delay: null })
    renderScreen()

    await user.click(screen.getByRole('switch', { name: /Only passengers of my gender/ }))

    expect(
      await screen.findByText(/no gender set, so this filter would hide the ride/),
    ).toBeVisible()
  })
})
