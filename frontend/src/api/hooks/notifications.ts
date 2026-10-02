import type { QueryClient } from '@tanstack/react-query'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { notificationKeys } from '../keys'
import type { Notification } from '../types'

/** The Notifications tab, newest first (openapi: listNotifications). */
export function useNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: notificationKeys.list(unreadOnly),
    queryFn: ({ signal }) =>
      api.get<Notification[]>('/notifications', { unread_only: unreadOnly }, signal),
  })
}

/** The bottom-nav badge. Polled, and nudged live by the WS push. */
export function useUnreadCount() {
  return useQuery({
    queryKey: notificationKeys.unreadCount,
    queryFn: ({ signal }) =>
      api.get<{ count: number }>('/notifications/unread-count', undefined, signal),
    select: (body) => body.count,
    refetchInterval: 60_000,
  })
}

/** Every write here only moves `is_read` or the list's length, not any ride data. */
function invalidateNotifications(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: notificationKeys.all })
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (notificationId: number) =>
      api.post<Notification>(`/notifications/${notificationId}/read`),
    onSuccess: () => invalidateNotifications(queryClient),
  })
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<void>('/notifications/read-all'),
    onSuccess: () => invalidateNotifications(queryClient),
  })
}

export function useClearNotifications() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<void>('/notifications'),
    onSuccess: () => invalidateNotifications(queryClient),
  })
}
