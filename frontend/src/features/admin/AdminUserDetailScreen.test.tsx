import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedAdmin, seedRating, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { AdminUserDetailScreen } from './AdminUserDetailScreen'

function renderScreen(me: UserMe, route: string) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/admin/users/:userId" element={<AdminUserDetailScreen />} />
    </Routes>,
    { route },
  )
}

describe('Admin user detail', () => {
  it('shows the rides driven and ratings received by the user', async () => {
    const admin = seedOnboardedAdmin()
    seedRide({ driver_id: 2, start_address: 'Dizengoff Street 50, Tel Aviv-Yafo, Israel' })
    seedRating({ to_user_id: 2, from_user_id: 3, score: 5, comment: 'Great driver' })
    renderScreen(admin, '/app/admin/users/2')

    expect(await screen.findByText(/Dizengoff Street 50/)).toBeVisible()
    expect(await screen.findByText('Great driver')).toBeVisible()
  })

  it('deactivates another user after confirming', async () => {
    const user = userEvent.setup()
    const admin = seedOnboardedAdmin()
    renderScreen(admin, '/app/admin/users/2')

    await user.click(await screen.findByRole('button', { name: 'Deactivate' }))
    await user.click(await screen.findByRole('button', { name: 'Deactivate' }))

    expect(await screen.findByText('Reactivate')).toBeVisible()
    expect(db.users.find((candidate) => candidate.id === 2)?.is_active).toBe(false)
  })

  it('will not let an admin deactivate their own account', async () => {
    const admin = seedOnboardedAdmin()
    renderScreen(admin, `/app/admin/users/${admin.id}`)

    expect(await screen.findByText("You can't deactivate your own account.")).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument()
  })
})
