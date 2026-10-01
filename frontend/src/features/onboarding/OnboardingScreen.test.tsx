import { Route, Routes } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { db } from '../../mocks/db'
import { renderWithProviders } from '../../test/utils'
import { OnboardingScreen } from './OnboardingScreen'

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => ({
    user: {
      fullName: 'Dvir Levi',
      primaryEmailAddress: { emailAddress: 'dvir@example.com' },
    },
  }),
}))

function renderScreen() {
  return renderWithProviders(
    <Routes>
      <Route path="/onboarding" element={<OnboardingScreen />} />
      <Route path="/app" element={<p>Signed in</p>} />
    </Routes>,
    { route: '/onboarding' },
  )
}

describe('onboarding', () => {
  it('offers the name Clerk already collected', async () => {
    renderScreen()
    expect(await screen.findByLabelText('Name')).toHaveValue('Dvir Levi')
  })

  it('refuses a date of birth under 18 before calling the API', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.type(await screen.findByLabelText(/Date of birth/), '2015-05-04')
    await user.click(screen.getByRole('checkbox', { name: /accept the RideMatch terms/i }))
    await user.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(await screen.findByText('You must be 18 or older to use RideMatch.')).toBeVisible()
    expect(db.me).toBeNull()
  })

  it('requires the terms before it will submit', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.type(await screen.findByLabelText(/Date of birth/), '1996-02-11')
    await user.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(await screen.findByText('Accept the terms to continue.')).toBeVisible()
    expect(db.me).toBeNull()
  })

  it('creates the profile and moves on to the app', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.type(await screen.findByLabelText(/Date of birth/), '1996-02-11')
    await user.click(screen.getByRole('checkbox', { name: /accept the RideMatch terms/i }))
    await user.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(await screen.findByText('Signed in')).toBeVisible()
    await waitFor(() => expect(db.me?.name).toBe('Dvir Levi'))
    expect(db.me?.vehicle).toBeNull()
  })

  it('sends the car when the driver adds one', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.type(await screen.findByLabelText(/Date of birth/), '1996-02-11')
    await user.click(screen.getByRole('checkbox', { name: /add my car now/i }))
    await user.type(screen.getByLabelText('Make'), 'Toyota')
    await user.type(screen.getByLabelText('Model'), 'Corolla')
    await user.type(screen.getByLabelText('Colour'), 'White')
    await user.type(screen.getByLabelText(/Licence plate/), '12-345-67')
    await user.click(screen.getByRole('checkbox', { name: /accept the RideMatch terms/i }))
    await user.click(screen.getByRole('button', { name: 'Create profile' }))

    await waitFor(() =>
      expect(db.me?.vehicle).toEqual({
        make: 'Toyota',
        model: 'Corolla',
        color: 'White',
        plate: '12-345-67',
      }),
    )
  })
})
