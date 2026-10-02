import type { QueryClient } from '@tanstack/react-query'
import { requestKeys, rideKeys } from './keys'

/**
 * Rides and requests are one system: approving a request moves a seat, which
 * changes the ride's `available_seats` and possibly its status, which in turn
 * changes what the passenger's My Trips row says. Rather than guess which of
 * the eight lists a given action touched, every write refreshes both roots.
 */
export function invalidateRidesAndRequests(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: rideKeys.all })
  void client.invalidateQueries({ queryKey: requestKeys.all })
}
