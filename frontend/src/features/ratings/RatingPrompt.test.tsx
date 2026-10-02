import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { seedOnboardedDriver, seedRequest, seedRide } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { RatingPrompt } from './RatingPrompt'

describe('the post-ride rating prompt', () => {
  it('stays empty with no completed rides', async () => {
    const me = seedOnboardedDriver()
    const { container } = renderAsUser(me, <RatingPrompt />)

    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('offers to rate the one passenger still owed a rating', async () => {
    const me = seedOnboardedDriver()
    const ride = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: ride.id, passenger_id: 3, status: 'approved' })
    renderAsUser(me, <RatingPrompt />)

    expect(await screen.findByText('Rate your ride')).toBeVisible()
    expect(screen.getByText(/How was Omer Katz as a passenger/)).toBeVisible()
    expect(screen.getByRole('link')).toHaveAttribute('href', `/app/rate/${ride.id}/3`)
  })

  it('counts every ride still owed a rating', async () => {
    const me = seedOnboardedDriver()
    const first = seedRide({ driver_id: me.id, status: 'completed' })
    const second = seedRide({ driver_id: me.id, status: 'completed' })
    seedRequest({ ride_id: first.id, passenger_id: 3, status: 'approved' })
    seedRequest({ ride_id: second.id, passenger_id: 3, status: 'approved' })
    renderAsUser(me, <RatingPrompt />)

    expect(await screen.findByText('Rate 2 rides')).toBeVisible()
  })
})
