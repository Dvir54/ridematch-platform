import type { Ride } from '../api/types'

/** "2 of 3 seats free" — the number a driver and a passenger both scan for. */
export function seatsLine(ride: Ride): string {
  if (ride.available_seats === 0) return `No seats left of ${ride.capacity}`
  return `${ride.available_seats} of ${ride.capacity} seats free`
}
