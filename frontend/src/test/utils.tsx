import type { ReactElement, ReactNode } from 'react'
import { render } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { createQueryClient } from '../api/queryClient'
import { CurrentUserProvider } from '../auth/CurrentUserProvider'
import type { UserMe } from '../api/types'

export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const queryClient = createQueryClient()

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[route]}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </MemoryRouter>
    )
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper }) }
}

/**
 * Most screens sit inside `<RequireProfile/>`, which means `useCurrentUser()`
 * always has someone. Tests mount that context directly instead of going through
 * Clerk.
 */
export function renderAsUser(user: UserMe, ui: ReactElement, { route = '/' } = {}) {
  return renderWithProviders(<CurrentUserProvider user={user}>{ui}</CurrentUserProvider>, {
    route,
  })
}
