import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { seedOnboardedMe, seedRating } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { PublicProfileScreen } from './PublicProfileScreen'

function renderScreen(me: UserMe, route: string) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/users/:userId" element={<PublicProfileScreen />} />
    </Routes>,
    { route },
  )
}

describe('a public profile', () => {
  it('shows ratings, the car and what people said', async () => {
    const me = seedOnboardedMe()
    seedRating({
      ride_id: 101,
      from_user_id: 3,
      to_user_id: 2,
      role_rated: 'driver',
      score: 5,
      comment: 'Smooth drive',
      tags: ['on_time'],
    })
    renderScreen(me, '/app/users/2')

    expect(await screen.findByText('Noa Berman')).toBeVisible()
    expect(screen.getByText('4.8 from 37 ratings')).toBeVisible()
    expect(screen.getByText('Not rated yet')).toBeVisible()
    expect(screen.getByText('White Toyota Corolla')).toBeVisible()

    expect(await screen.findByText('Omer Katz')).toBeVisible()
    expect(screen.getByText('Smooth drive')).toBeVisible()
    expect(screen.getByText('on time')).toBeVisible()
  })

  it('shows an empty state with nobody rated yet', async () => {
    const me = seedOnboardedMe()
    renderScreen(me, '/app/users/3')

    expect(await screen.findByText('Omer Katz')).toBeVisible()
    expect(await screen.findByText('No ratings yet')).toBeVisible()
  })

  it('refuses a link that does not name a user', async () => {
    const me = seedOnboardedMe()
    renderScreen(me, '/app/users/not-a-number')

    expect(await screen.findByText('No such profile')).toBeVisible()
  })
})
