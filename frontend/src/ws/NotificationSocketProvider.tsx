import { useEffect } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { useQueryClient } from '@tanstack/react-query'
import { invalidateRidesAndRequests } from '../api/invalidate'
import { notificationKeys } from '../api/keys'
import { env } from '../env'
import { NotificationSocket } from './socketClient'

/**
 * Keeps one live socket open for as long as the app shell is mounted
 * (CONTRACT §6). Every push means a notification exists and something it
 * refers to just changed, so rather than guess which of the rides/requests
 * lists a given event touched, it just invalidates both roots the same way
 * every other mutation in this app does (`invalidateRidesAndRequests`).
 */
export function NotificationSocketProvider() {
  const { getToken } = useAuth()
  const queryClient = useQueryClient()

  useEffect(() => {
    const socket = new NotificationSocket({
      url: env.wsUrl,
      getToken: () => getToken(),
      onNotification: () => {
        void queryClient.invalidateQueries({ queryKey: notificationKeys.all })
        invalidateRidesAndRequests(queryClient)
      },
    })
    socket.connect()
    return () => socket.disconnect()
  }, [getToken, queryClient])

  return null
}
