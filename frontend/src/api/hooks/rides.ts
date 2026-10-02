import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { invalidateRidesAndRequests } from '../invalidate'
import { requestKeys, rideKeys, statusParam } from '../keys'
import type { Ride, RideCreate, RideStatus, RideUpdate } from '../types'

/** Rides the caller drives, departure ascending (openapi: listMyRides). */
export function useMyRides(statuses?: readonly RideStatus[]) {
  return useQuery({
    queryKey: rideKeys.mine(statuses),
    queryFn: ({ signal }) =>
      api.get<Ride[]>('/rides/mine', { status: statusParam(statuses) }, signal),
  })
}

export function useRide(rideId: number | undefined) {
  return useQuery({
    queryKey: rideKeys.detail(rideId ?? 0),
    queryFn: ({ signal }) => api.get<Ride>(`/rides/${rideId}`, undefined, signal),
    enabled: rideId !== undefined,
  })
}

export function useCreateRide() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RideCreate) => api.post<Ride>('/rides', body),
    onSuccess: (ride) => {
      queryClient.setQueryData(rideKeys.detail(ride.id), ride)
      invalidateRidesAndRequests(queryClient)
    },
  })
}

export function useUpdateRide(rideId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RideUpdate) => api.patch<Ride>(`/rides/${rideId}`, body),
    onSuccess: (ride) => {
      queryClient.setQueryData(rideKeys.detail(ride.id), ride)
      invalidateRidesAndRequests(queryClient)
    },
  })
}

/** cancel / start / complete all answer with the updated ride, so they share a hook. */
type RideAction = 'cancel' | 'start' | 'complete'

function useRideAction(rideId: number, action: RideAction) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Ride>(`/rides/${rideId}/${action}`),
    onSuccess: (ride) => {
      queryClient.setQueryData(rideKeys.detail(ride.id), ride)
      // Starting a ride auto-rejects pending requests and completing it opens
      // ratings, so the request lists are stale either way (CONTRACT §3).
      void queryClient.invalidateQueries({ queryKey: requestKeys.all })
      void queryClient.invalidateQueries({ queryKey: rideKeys.all })
    },
  })
}

export const useCancelRide = (rideId: number) => useRideAction(rideId, 'cancel')
export const useStartRide = (rideId: number) => useRideAction(rideId, 'start')
export const useCompleteRide = (rideId: number) => useRideAction(rideId, 'complete')
