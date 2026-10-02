import type { Ride, RideRequest, UserMe, UserPublic } from '../api/types'
import type { RequestRow, RideRow } from './db'
import { db, findUser } from './db'

export function toPublic(user: UserMe): UserPublic {
  return {
    id: user.id,
    name: user.name,
    driver_rating: user.driver_rating ?? null,
    driver_rating_count: user.driver_rating_count,
    passenger_rating: user.passenger_rating ?? null,
    passenger_rating_count: user.passenger_rating_count,
    vehicle: user.vehicle
      ? { make: user.vehicle.make, model: user.vehicle.model, color: user.vehicle.color }
      : null,
    created_at: user.created_at,
  }
}

const UNKNOWN_DRIVER: UserPublic = {
  id: 0,
  name: 'Unknown driver',
  driver_rating: null,
  driver_rating_count: 0,
  passenger_rating: null,
  passenger_rating_count: 0,
  vehicle: null,
  created_at: new Date(0).toISOString(),
}

/**
 * The plate is private: the driver sees it, and so does a passenger whose
 * request on *this* ride is approved. Everyone else gets null (D14).
 */
function plateFor(row: RideRow, viewerId: number | null): string | null {
  const driver = findUser(row.driver_id)
  const plate = driver?.vehicle?.plate ?? null
  if (!plate || viewerId === null) return null
  if (viewerId === row.driver_id) return plate

  const approved = db.requests.some(
    (request) =>
      request.ride_id === row.id &&
      request.passenger_id === viewerId &&
      request.status === 'approved',
  )
  return approved ? plate : null
}

export function toRide(row: RideRow, viewerId: number | null): Ride {
  const driver = findUser(row.driver_id)
  return {
    id: row.id,
    driver: driver ? toPublic(driver) : UNKNOWN_DRIVER,
    start_lat: row.start_lat,
    start_lng: row.start_lng,
    start_address: row.start_address,
    end_lat: row.end_lat,
    end_lng: row.end_lng,
    end_address: row.end_address,
    departure_time: row.departure_time,
    capacity: row.capacity,
    available_seats: row.available_seats,
    price_per_seat: row.price_per_seat,
    status: row.status,
    preferences: { ...row.preferences },
    notes: row.notes,
    driver_vehicle_plate: plateFor(row, viewerId),
    created_at: row.created_at,
    updated_at: row.updated_at,
  }
}

export function toRideRequest(row: RequestRow, viewerId: number | null): RideRequest {
  const ride = db.rides.find((candidate) => candidate.id === row.ride_id)
  const passenger = findUser(row.passenger_id)
  return {
    id: row.id,
    ride: ride
      ? toRide(ride, viewerId)
      : toRide(
          {
            id: row.ride_id,
            driver_id: 0,
            start_lat: 0,
            start_lng: 0,
            start_address: 'Unknown',
            end_lat: 0,
            end_lng: 0,
            end_address: 'Unknown',
            departure_time: row.requested_at,
            capacity: 0,
            available_seats: 0,
            price_per_seat: '0.00',
            status: 'cancelled',
            preferences: { smoking: false, pets: false, music: true, gender_only: false },
            notes: null,
            created_at: row.requested_at,
            updated_at: row.requested_at,
          },
          viewerId,
        ),
    passenger: passenger ? toPublic(passenger) : UNKNOWN_DRIVER,
    seats_requested: row.seats_requested,
    status: row.status,
    requested_at: row.requested_at,
    responded_at: row.responded_at,
  }
}
