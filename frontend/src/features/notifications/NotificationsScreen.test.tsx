import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { seedNotification, seedOnboardedMe } from '../../mocks/db'
import { renderAsUser } from '../../test/utils'
import { NotificationsScreen } from './NotificationsScreen'

describe('Alerts', () => {
  it('shows the empty state with nothing seeded', async () => {
    const me = seedOnboardedMe()
    renderAsUser(me, <NotificationsScreen />)

    expect(await screen.findByText('No alerts')).toBeVisible()
  })

  it('lists alerts newest first and marks one read', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    seedNotification({
      id: 1,
      title: 'Request received',
      message: 'Omer asked for a seat.',
      created_at: '2026-10-01T08:00:00Z',
    })
    seedNotification({
      id: 2,
      title: 'Seat approved',
      message: 'Your seat was approved.',
      created_at: '2026-10-01T09:00:00Z',
    })
    renderAsUser(me, <NotificationsScreen />)

    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Seat approved')
    expect(rows[1]).toHaveTextContent('Request received')

    await user.click(within(rows[0]).getByRole('button', { name: 'Mark read' }))
    expect(
      await within(rows[0]).findByText('Seat approved'),
    ).toBeVisible()
    expect(within(rows[0]).queryByRole('button', { name: 'Mark read' })).not.toBeInTheDocument()
  })

  it('marks every alert read at once', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    seedNotification({ id: 1, title: 'One' })
    seedNotification({ id: 2, title: 'Two' })
    renderAsUser(me, <NotificationsScreen />)

    await screen.findByText('One')
    await user.click(screen.getByRole('button', { name: 'Mark all read' }))

    expect(await screen.findByRole('button', { name: 'Mark all read' })).toBeDisabled()
    expect(screen.queryAllByRole('button', { name: 'Mark read' })).toHaveLength(0)
  })

  it('clears every alert after confirming', async () => {
    const user = userEvent.setup()
    const me = seedOnboardedMe()
    seedNotification({ id: 1, title: 'One' })
    renderAsUser(me, <NotificationsScreen />)

    await screen.findByText('One')
    await user.click(screen.getByRole('button', { name: 'Clear all' }))
    await user.click(await screen.findByRole('button', { name: 'Delete them all' }))

    expect(await screen.findByText('No alerts')).toBeVisible()
  })
})
