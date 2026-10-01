import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { isApiError } from '../errors'
import type { OnboardingRequest, UserMe, UserPatch } from '../types'

/**
 * `GET /users/me` answers three different things, and only one of them is a
 * failure. ONBOARDING_REQUIRED and ACCOUNT_DEACTIVATED are states the app
 * routes on (CONTRACT §2), so they come back as data.
 */
export type Session =
  | { status: 'ready'; user: UserMe }
  | { status: 'onboarding_required' }
  | { status: 'deactivated' }

export const sessionKey = ['session'] as const

async function fetchSession(): Promise<Session> {
  try {
    return { status: 'ready', user: await api.get<UserMe>('/users/me') }
  } catch (error) {
    if (isApiError(error) && error.is('ONBOARDING_REQUIRED')) {
      return { status: 'onboarding_required' }
    }
    if (isApiError(error) && error.is('ACCOUNT_DEACTIVATED')) {
      return { status: 'deactivated' }
    }
    throw error
  }
}

export function useSession(enabled = true) {
  return useQuery({ queryKey: sessionKey, queryFn: fetchSession, enabled })
}

export function useCompleteOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OnboardingRequest) => api.post<UserMe>('/users/me/onboarding', body),
    onSuccess: (user) => {
      const session: Session = { status: 'ready', user }
      queryClient.setQueryData(sessionKey, session)
    },
  })
}

export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UserPatch) => api.patch<UserMe>('/users/me', body),
    onSuccess: (user) => {
      const session: Session = { status: 'ready', user }
      queryClient.setQueryData(sessionKey, session)
    },
  })
}
