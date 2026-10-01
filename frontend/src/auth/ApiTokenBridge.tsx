import { useEffect } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { setTokenProvider } from '../api/client'

/**
 * Hands the API client a way to fetch a fresh Clerk token. Rendered above the
 * routes so the provider is installed before any screen queries the backend.
 */
export function ApiTokenBridge() {
  const { getToken } = useAuth()

  useEffect(() => {
    setTokenProvider(() => getToken())
  }, [getToken])

  return null
}
