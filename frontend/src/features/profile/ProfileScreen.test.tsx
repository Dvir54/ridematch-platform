import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  db,
  seedOnboardedDriver,
  seedOnboardedMe,
  seedRequest,
  seedRide,
} from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { ProfileScreen } from './ProfileScreen'

vi.mock('@clerk/clerk-react', () => ({
  useClerk: () => ({ openUserProfile: () => {}, signOut: () => {} }),
}))

describe('the car on Profile', () => {
  it('adds a car with the same fields and validation as onboarding', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    renderAsUser(me, <ProfileScreen />)

    expect(screen.getByText(/No car added/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Add your car' }))
    await user.click(screen.getByRole('button', { name: 'Save car' }))
    expect(await screen.findAllByText('Required.')).toHaveLength(3)
    expect(screen.getByText('Enter the plate as it appears on the car.')).toBeVisible()

    await user.type(screen.getByLabelText('Make'), 'Toyota')
    await user.type(screen.getByLabelText('Model'), 'Corolla')
    await user.type(screen.getByLabelText('Colour'), 'White')
    await user.type(screen.getByLabelText('Licence plate'), '12-345-67')
    await user.click(screen.getByRole('button', { name: 'Save car' }))

    // The context's user is a static prop in tests (see test/utils.tsx), so the
    // write is checked on the mock store rather than the re-rendered screen —
    // the same convention RoleSelectionScreen.test.tsx uses for useUpdateMe.
    await waitFor(() =>
      expect(db.me?.vehicle).toMatchObject({ make: 'Toyota', model: 'Corolla', color: 'White' }),
    )
    expect(screen.queryByRole('button', { name: 'Save car' })).not.toBeInTheDocument()
  })

  it('edits an existing car, prefilling its current fields', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    renderAsUser(me, <ProfileScreen />)

    await user.click(screen.getByRole('button', { name: 'Edit car' }))
    expect(screen.getByLabelText('Make')).toHaveValue('Mazda')

    await user.clear(screen.getByLabelText('Model'))
    await user.type(screen.getByLabelText('Model'), 'CX-5')
    await user.click(screen.getByRole('button', { name: 'Save car' }))

    // The context's user is a static prop in tests (see test/utils.tsx), so the
    // write is checked on the mock store rather than the re-rendered screen —
    // the same convention RoleSelectionScreen.test.tsx uses for useUpdateMe.
    await waitFor(() => expect(db.me?.vehicle?.model).toBe('CX-5'))
  })

  it('removes a car, and shows the 409 when upcoming rides still need one', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedDriver()
    seedRide({ driver_id: me.id, status: 'upcoming' })
    renderAsUser(me, <ProfileScreen />)

    await user.click(screen.getByRole('button', { name: 'Remove car' }))
    await user.click(screen.getByRole('button', { name: 'Remove it' }))

    expect(
      await screen.findByText('Add your car to your profile before offering a ride.'),
    ).toBeVisible()
    expect(db.me?.vehicle).not.toBeNull()
  })
})

describe('trip stats on Profile', () => {
  it('counts both sides of the trip record', async () => {
    const me = seedOnboardedDriver()
    seedRide({ driver_id: me.id, status: 'completed' })
    seedRide({ driver_id: me.id, status: 'upcoming' })
    const someoneElsesRide = seedRide({ driver_id: 2, status: 'completed' })
    seedRequest({ ride_id: someoneElsesRide.id, passenger_id: me.id, status: 'approved' })
    renderAsUser(me, <ProfileScreen />)

    const driverHeading = await screen.findByRole('heading', { name: 'As a driver', level: 3 })
    const driverStats = driverHeading.closest('div') as HTMLElement
    expect(driverStats).toHaveTextContent('2')
    expect(driverStats).toHaveTextContent('Rides offered')

    const passengerHeading = screen.getByRole('heading', { name: 'As a passenger', level: 3 })
    const passengerStats = passengerHeading.closest('div') as HTMLElement
    expect(passengerStats).toHaveTextContent('Trips requested')
    expect(passengerStats).toHaveTextContent('1')
  })
})
