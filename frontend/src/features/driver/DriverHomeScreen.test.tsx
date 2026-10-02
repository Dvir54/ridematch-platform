import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { seedOnboardedDriver, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { DriverHomeScreen } from './DriverHomeScreen'

describe('the driver Home screen', () => {
  it('shows at-a-glance stats and the rating prompt for a completed ride', async () => {
    const me = seedOnboardedDriver()
    const completed = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: completed.id, passenger_id: 3, status: 'approved' })
    renderAsUser(me, <DriverHomeScreen />)

    expect(await screen.findByText('Completed')).toBeVisible()
    expect(await screen.findByText('Rate your ride')).toBeVisible()
  })
})
