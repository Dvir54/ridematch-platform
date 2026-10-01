import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { isApiError } from './errors'
import { sessionKey } from './keys'

/**
 * Every authenticated endpoint can answer 403 ONBOARDING_REQUIRED or
 * ACCOUNT_DEACTIVATED, not just GET /users/me (openapi.yaml documents this on
 * all of them). Whichever call hits it, the session is stale, so re-read it and
 * let the route guards move the user to onboarding or the deactivated screen.
 */
function recheckSessionOn403(client: QueryClient, error: unknown): void {
  if (isApiError(error) && error.is('ONBOARDING_REQUIRED', 'ACCOUNT_DEACTIVATED')) {
    void client.invalidateQueries({ queryKey: sessionKey })
  }
}

/** A 4xx is an answer, not a hiccup — only retry what might succeed next time. */
export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => recheckSessionOn403(client, error) }),
    mutationCache: new MutationCache({ onError: (error) => recheckSessionOn403(client, error) }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (isApiError(error) && error.status >= 400 && error.status < 500) return false
          return failureCount < 2
        },
      },
      mutations: { retry: false },
    },
  })

  return client
}
