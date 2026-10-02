import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { isApiError } from '../errors'
import { sessionKey, statsKey, userKeys } from '../keys'
import type { OnboardingRequest, UserMe, UserPublic, UserStats, UserUpdate } from '../types'

/**
 * `GET /users/me` answers three different things, and only one of them is a
 * failure. ONBOARDING_REQUIRED and ACCOUNT_DEACTIVATED are states the app
 * routes on (CONTRACT §2), so they come back as data.
 */
export type Session =
  | { status: 'ready'; user: UserMe }
  | { status: 'onboarding_required' }
  | { status: 'deactivated' }

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
    mutationFn: (body: UserUpdate) => api.patch<UserMe>('/users/me', body),
    onSuccess: (user) => {
      const session: Session = { status: 'ready', user }
      queryClient.setQueryData(sessionKey, session)
    },
  })
}

/** Counters for the driver Home, passenger Home and Profile screens. */
export function useMyStats() {
  return useQuery({
    queryKey: statsKey,
    queryFn: ({ signal }) => api.get<UserStats>('/users/me/stats', undefined, signal),
  })
}

/** A public profile — anyone's, including the caller's own (openapi: getUserPublic). */
export function useUserPublic(userId: number | undefined) {
  return useQuery({
    queryKey: userKeys.detail(userId ?? 0),
    queryFn: ({ signal }) => api.get<UserPublic>(`/users/${userId}`, undefined, signal),
    enabled: userId !== undefined,
  })
}
