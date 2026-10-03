import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { db } from '../../mocks/db'
import { server } from '../../mocks/node'
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
  it('links the terms and privacy policy from the consent checkbox', async () => {
    renderScreen()
    expect(await screen.findByRole('link', { name: 'terms of service' })).toHaveAttribute(
      'href',
      '/terms',
    )
    expect(screen.getByRole('link', { name: 'privacy policy' })).toHaveAttribute(
      'href',
      '/privacy',
    )
  })

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

/**
 * A VALIDATION_ERROR normally speaks through the fields it names, and the banner
 * stays hidden so the reason is not said twice. That only works while every field
 * the server can name has an input here — otherwise the submit looked like it did
 * nothing at all. Contract 0.4.5 says `field` may get more specific over time, so
 * the fallback has to hold for names this form has never seen.
 */
describe('a 422 naming a field the form did not expect', () => {
  function rejectOnboardingWith(details: { field: string; message: string }[]) {
    server.use(
      http.post('*/users/me/onboarding', () =>
        HttpResponse.json(
          { code: 'VALIDATION_ERROR', message: 'Some details need fixing.', details },
          { status: 422 },
        ),
      ),
    )
  }

  async function fillAndSubmit({ withVehicle = false } = {}) {
    const user = userEvent.setup()
    renderScreen()
    await user.type(await screen.findByLabelText('Date of birth'), '1996-02-11')
    await user.click(screen.getByLabelText(/I accept the RideMatch terms/))

    if (withVehicle) {
      await user.click(screen.getByLabelText(/add my car now/))
      await user.type(screen.getByLabelText('Make'), 'Mazda')
      await user.type(screen.getByLabelText('Model'), '3')
      await user.type(screen.getByLabelText('Colour'), 'Grey')
      await user.type(screen.getByLabelText('Licence plate'), 'AB')
    }

    await user.click(screen.getByRole('button', { name: 'Create profile' }))
  }

  it('lands a vehicle sub-field on the input that owns it', async () => {
    // The server can only name `vehicle.plate` on a body that carried a vehicle,
    // which is exactly when that input is on screen.
    rejectOnboardingWith([{ field: 'body.vehicle.plate', message: 'A plate needs 2 characters.' }])
    await fillAndSubmit({ withVehicle: true })

    expect(await screen.findByText('A plate needs 2 characters.')).toBeVisible()
    expect(screen.getByLabelText('Licence plate')).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows a field it cannot place rather than failing silently', async () => {
    rejectOnboardingWith([
      { field: 'body.preferences.language', message: 'That language is not supported.' },
    ])
    await fillAndSubmit()

    // Previously: no field error set, banner suppressed for VALIDATION_ERROR, so
    // the form appeared to do nothing.
    expect(await screen.findByText('That language is not supported.')).toBeVisible()
    expect(screen.getByText('Some details need fixing.')).toBeVisible()
  })

  it('keeps the banner hidden when every named field has its own input', async () => {
    rejectOnboardingWith([{ field: 'body.name', message: 'That name is too long.' }])
    await fillAndSubmit()

    expect(await screen.findByText('That name is too long.')).toBeVisible()
    expect(screen.queryByText('Some details need fixing.')).not.toBeInTheDocument()
  })
})
