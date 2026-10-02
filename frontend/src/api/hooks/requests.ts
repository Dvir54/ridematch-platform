import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { invalidateRidesAndRequests } from '../invalidate'
import { requestKeys, rideKeys, statusParam } from '../keys'
import type { RequestStatus, RideRequest, RideRequestCreate } from '../types'

/** The passenger's own requests — My Trips. Newest first. */
export function useMyRequests(statuses?: readonly RequestStatus[]) {
  return useQuery({
    queryKey: requestKeys.mine(statuses),
    queryFn: ({ signal }) =>
      api.get<RideRequest[]>('/requests/mine', { status: statusParam(statuses) }, signal),
  })
}

/** Requests across all of the caller's rides — the driver's Requests tab. */
export function useIncomingRequests(status: RequestStatus = 'pending') {
  return useQuery({
    queryKey: requestKeys.incoming(status),
    queryFn: ({ signal }) => api.get<RideRequest[]>('/requests/incoming', { status }, signal),
  })
}

/** Requests on one ride. Driver only (openapi: listRideRequests). */
export function useRideRequests(rideId: number | undefined, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: rideKeys.requests(rideId ?? 0),
    queryFn: ({ signal }) => api.get<RideRequest[]>(`/rides/${rideId}/requests`, undefined, signal),
    enabled: rideId !== undefined && options.enabled !== false,
  })
}

export function useCreateRequest(rideId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RideRequestCreate) =>
      api.post<RideRequest>(`/rides/${rideId}/requests`, body),
    onSuccess: (created) => {
      queryClient.setQueryData(requestKeys.detail(created.id), created)
      invalidateRidesAndRequests(queryClient)
    },
  })
}

type RequestAction = 'approve' | 'reject' | 'cancel'

function useRequestAction(action: RequestAction) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (requestId: number) => api.post<RideRequest>(`/requests/${requestId}/${action}`),
    onSuccess: (updated) => {
      queryClient.setQueryData(requestKeys.detail(updated.id), updated)
      invalidateRidesAndRequests(queryClient)
    },
  })
}

/** Driver actions. Approve can still lose the last seat → 409 NOT_ENOUGH_SEATS. */
export const useApproveRequest = () => useRequestAction('approve')
export const useRejectRequest = () => useRequestAction('reject')
/** Passenger action. Approved seats lock an hour out → 409 TOO_LATE_TO_CANCEL. */
export const useCancelRequest = () => useRequestAction('cancel')
