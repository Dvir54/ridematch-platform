import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { seedOnboardedMe, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { PassengerHomeScreen } from './PassengerHomeScreen'

describe('the passenger Home screen', () => {
  it('shows at-a-glance stats and the rating prompt for a completed trip', async () => {
    const me = seedOnboardedMe()
    const ride = seedRide({ driver_id: 2, status: 'completed' })
    seedRequest({ ride_id: ride.id, passenger_id: me.id, status: 'approved' })
    renderAsUser(me, <PassengerHomeScreen />)

    expect(await screen.findByText('Completed')).toBeVisible()
    expect(await screen.findByText('Rate your ride')).toBeVisible()
  })
})
