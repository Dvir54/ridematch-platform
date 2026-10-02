import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import type { AdminRidesParams, AdminUsersParams } from '../keys'
import { adminKeys, statusParam } from '../keys'
import type { AdminUserDetail, AnalyticsSummary, Ride, UserMe } from '../types'

/** `/admin/users` — search and filter, `X-Total-Count` drives pagination (CONTRACT §2). */
export function useAdminUsers(params: AdminUsersParams) {
  return useQuery({
    queryKey: adminKeys.users(params),
    queryFn: ({ signal }) =>
      api.getList<UserMe>(
        '/admin/users',
        {
          q: params.q,
          is_active: params.is_active,
          is_admin: params.is_admin,
          limit: params.limit,
          offset: params.offset,
        },
        signal,
      ),
  })
}

export function useAdminUserDetail(userId: number | undefined) {
  return useQuery({
    queryKey: adminKeys.userDetail(userId ?? 0),
    queryFn: ({ signal }) => api.get<AdminUserDetail>(`/admin/users/${userId}`, undefined, signal),
    enabled: userId !== undefined,
  })
}

function useSetUserActive(active: boolean) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: number) =>
      api.post<UserMe>(`/admin/users/${userId}/${active ? 'reactivate' : 'deactivate'}`),
    onSuccess: (user) => {
      queryClient.setQueryData(adminKeys.userDetail(user.id), (current: AdminUserDetail | undefined) =>
        current ? { ...current, user } : current,
      )
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

/** Ends the user's Clerk sessions too (CONTRACT §2). Cannot target self → 409 CANNOT_DEACTIVATE_SELF. */
export const useDeactivateUser = () => useSetUserActive(false)
export const useReactivateUser = () => useSetUserActive(true)

/** `/admin/rides` — every ride platform-wide, filterable by status/driver/date. */
export function useAdminRides(params: AdminRidesParams) {
  return useQuery({
    queryKey: adminKeys.rides(params),
    queryFn: ({ signal }) =>
      api.getList<Ride>(
        '/admin/rides',
        {
          status: statusParam(params.status),
          driver_id: params.driver_id,
          from: params.from,
          to: params.to,
          limit: params.limit,
          offset: params.offset,
        },
        signal,
      ),
  })
}

export function useForceCancelRide() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ rideId, reason }: { rideId: number; reason: string }) =>
      api.post<Ride>(`/admin/rides/${rideId}/force-cancel`, { reason }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'rides'] })
    },
  })
}

export function useAdminAnalytics(from: string, to: string) {
  return useQuery({
    queryKey: adminKeys.analytics(from, to),
    queryFn: ({ signal }) =>
      api.get<AnalyticsSummary>('/admin/analytics', { from, to }, signal),
    enabled: Boolean(from) && Boolean(to),
  })
}
