import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { seedOnboardedAdmin } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { AdminUsersScreen } from './AdminUsersScreen'

function renderScreen(me: UserMe) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/admin/users" element={<AdminUsersScreen />} />
      <Route path="/app/admin/users/:userId" element={<p>User detail</p>} />
    </Routes>,
    { route: '/app/admin/users' },
  )
}

describe('Admin user management', () => {
  it('lists the seeded users', async () => {
    const admin = seedOnboardedAdmin()
    renderScreen(admin)

    expect(await screen.findByText('Noa Berman')).toBeVisible()
    expect(screen.getByText('Omer Katz')).toBeVisible()
  })

  it('filters by name or email as the admin searches', async () => {
    const user = userEvent.setup()
    const admin = seedOnboardedAdmin()
    renderScreen(admin)

    await screen.findByText('Noa Berman')
    await user.type(screen.getByLabelText('Search'), 'omer')

    expect(await screen.findByText('Omer Katz')).toBeVisible()
    expect(screen.queryByText('Noa Berman')).not.toBeInTheDocument()
  })

  it('opens a user into the detail screen', async () => {
    const user = userEvent.setup()
    const admin = seedOnboardedAdmin()
    renderScreen(admin)

    await user.click(await screen.findByRole('link', { name: /Noa Berman/ }))
    expect(await screen.findByText('User detail')).toBeVisible()
  })
})
