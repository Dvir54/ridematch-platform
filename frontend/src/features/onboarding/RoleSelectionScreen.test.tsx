import { Route, Routes } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CurrentUserProvider } from '../../auth/CurrentUserProvider'
import { db, seedOnboardedMe } from '../../mocks/db'
import { renderWithProviders } from '../../test/utils'
import { RoleSelectionScreen } from './RoleSelectionScreen'

function renderScreen() {
  const me = seedOnboardedMe()
  return renderWithProviders(
    <CurrentUserProvider user={me}>
      <Routes>
        <Route path="/role" element={<RoleSelectionScreen />} />
        <Route path="/app/driver" element={<p>Driver home</p>} />
        <Route path="/app/passenger" element={<p>Passenger home</p>} />
      </Routes>
    </CurrentUserProvider>,
    { route: '/role' },
  )
}

describe('role selection', () => {
  it('saves driving as the default mode and opens the driver home', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('button', { name: /Offer seats/ }))

    expect(await screen.findByText('Driver home')).toBeVisible()
    expect(db.me?.preferences.default_mode).toBe('driver')
  })

  it('saves riding as the default mode and opens the passenger home', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('button', { name: /Find a ride/ }))

    expect(await screen.findByText('Passenger home')).toBeVisible()
    expect(db.me?.preferences.default_mode).toBe('passenger')
  })

  it('keeps the rest of the preferences untouched when it patches the mode', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('button', { name: /Find a ride/ }))
    await screen.findByText('Passenger home')

    expect(db.me?.preferences.notifications).toEqual({
      email: true,
      push: true,
      websocket: true,
    })
    expect(db.me?.preferences.language).toBe('en')
  })
})
