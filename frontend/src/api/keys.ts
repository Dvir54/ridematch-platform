import type { RequestStatus, RideStatus } from './types'

/** Query keys shared between the hooks and the cache-wide error handling. */
export const sessionKey = ['session'] as const

/**
 * Status filters are part of the key, because `/rides/mine?status=upcoming` and
 * `?status=completed` are different lists, not different views of one list.
 */
function filter(statuses?: readonly string[]): string {
  return statuses?.length ? [...statuses].join(',') : 'all'
}

export const rideKeys = {
  all: ['rides'] as const,
  mine: (statuses?: readonly RideStatus[]) => ['rides', 'mine', filter(statuses)] as const,
  detail: (rideId: number) => ['rides', 'detail', rideId] as const,
  /** Nested under the ride, so refreshing a ride refreshes its passenger list. */
  requests: (rideId: number, status?: RequestStatus) =>
    ['rides', 'detail', rideId, 'requests', status ?? 'all'] as const,
}

export const requestKeys = {
  all: ['requests'] as const,
  mine: (statuses?: readonly RequestStatus[]) => ['requests', 'mine', filter(statuses)] as const,
  incoming: (status?: RequestStatus) => ['requests', 'incoming', status ?? 'pending'] as const,
  detail: (requestId: number) => ['requests', 'detail', requestId] as const,
}

/** Comma-separated status filter, as CONTRACT §2 specifies. Empty → omitted. */
export function statusParam(statuses?: readonly string[]): string | undefined {
  return statuses?.length ? [...statuses].join(',') : undefined
}
