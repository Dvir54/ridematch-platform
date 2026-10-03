import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../../test/utils'
import { PrivacyScreen, TermsScreen } from './LegalScreen'

function renderAt(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/terms" element={<TermsScreen />} />
      <Route path="/privacy" element={<PrivacyScreen />} />
    </Routes>,
    { route },
  )
}

describe('legal pages', () => {
  it.each([
    ['/terms', 'Terms of Service'],
    ['/privacy', 'Privacy Policy'],
  ])('%s renders without signing in, clearly marked as a placeholder', (route, title) => {
    renderAt(route)
    expect(screen.getByRole('heading', { name: title })).toBeVisible()
    expect(screen.getByRole('note')).toHaveTextContent(/placeholder/i)
    expect(screen.getByText('[privacy contact: to be provided]')).toBeVisible()
  })

  it('links each page to the other', () => {
    renderAt('/terms')
    const legal = screen.getByRole('navigation', { name: 'Legal' })
    expect(legal.querySelector('a[href="/privacy"]')).not.toBeNull()
    expect(legal.querySelector('a[href="/terms"]')).not.toBeNull()
  })
})
