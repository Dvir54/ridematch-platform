import { Route, Routes } from 'react-router-dom'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { db, seedOnboardedAdmin, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { AdminRidesScreen } from './AdminRidesScreen'

function renderScreen(me: UserMe) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/admin/rides" element={<AdminRidesScreen />} />
    </Routes>,
    { route: '/app/admin/rides' },
  )
}

/** Scopes queries to the card for one ride — the seed data always has a second
 * ride (id 101) alongside whatever a test adds, so unscoped queries are ambiguous. */
async function findRideCard(address: string) {
  const match = await screen.findByText(new RegExp(address))
  const card = match.closest('article')
  if (!card) throw new Error(`No ride card found for ${address}`)
  return within(card)
}

describe('Admin ride monitoring', () => {
  it('lists rides across every driver', async () => {
    const admin = seedOnboardedAdmin()
    const ride = seedRide({ driver_id: 2, start_address: 'Allenby Street 40, Tel Aviv-Yafo, Israel' })
    renderScreen(admin)

    const card = await findRideCard('Allenby Street 40')
    expect(card.getByText('Driven by Noa Berman')).toBeVisible()
    expect(db.rides.find((row) => row.id === ride.id)?.status).toBe('upcoming')
  })

  it('force-cancels a ride once a reason is given', async () => {
    const user = userEvent.setup()
    const admin = seedOnboardedAdmin()
    const ride = seedRide({ driver_id: 2, start_address: 'Carmel Street 9, Haifa, Israel' })
    renderScreen(admin)

    const card = await findRideCard('Carmel Street 9')
    await user.click(card.getByRole('button', { name: 'Force-cancel' }))
    await user.type(card.getByLabelText('Reason'), 'Reported unsafe driving')
    await user.click(card.getByRole('button', { name: 'Confirm cancel' }))

    expect(await card.findByText('Cancelled')).toBeVisible()
    expect(db.rides.find((row) => row.id === ride.id)?.status).toBe('cancelled')
  })

  it('will not confirm a force-cancel with no reason', async () => {
    const user = userEvent.setup()
    const admin = seedOnboardedAdmin()
    seedRide({ driver_id: 2, start_address: 'Yafo Street 3, Jerusalem, Israel' })
    renderScreen(admin)

    const card = await findRideCard('Yafo Street 3')
    await user.click(card.getByRole('button', { name: 'Force-cancel' }))
    expect(card.getByRole('button', { name: 'Confirm cancel' })).toBeDisabled()
  })
})
