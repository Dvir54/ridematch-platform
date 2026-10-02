import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { UserMe } from '../../api/types'
import { seedOnboardedAdmin, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { AdminAnalyticsScreen } from './AdminAnalyticsScreen'

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

function renderScreen(me: UserMe) {
  return renderAsUser(
    me,
    <Routes>
      <Route path="/app/admin/analytics" element={<AdminAnalyticsScreen />} />
    </Routes>,
    { route: '/app/admin/analytics' },
  )
}

describe('Admin analytics', () => {
  it('computes the completion rate for rides departing in the default range', async () => {
    const admin = seedOnboardedAdmin()
    seedRide({ driver_id: 2, status: 'completed', departure_time: hoursFromNow(-5) })
    seedRide({ driver_id: 2, status: 'cancelled', departure_time: hoursFromNow(-3) })
    renderScreen(admin)

    expect(await screen.findByText('Completion rate: 50%')).toBeVisible()
  })
})
