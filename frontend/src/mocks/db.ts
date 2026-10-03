import type {
  Notification,
  NotificationPrefs,
  NotificationType,
  RidePreferences,
  RideStatus,
  RequestStatus,
  RoleRated,
  UserMe,
  UserPreferences,
} from '../api/types'

/**
 * A tiny in-memory stand-in for the backend, shaped exactly like
 * contracts/openapi.yaml. It exists so screens can be built and tested before
 * @backend ships an endpoint — not as a second source of truth.
 *
 * Rides and requests are stored as *rows*, the way the real tables are, and
 * projected into the API shapes on read (`project.ts`). That keeps embedded
 * objects such as `RideRequest.ride` from going stale the moment a seat moves,
 * and it is the only way `driver_vehicle_plate` can follow its visibility rule.
 */
export const defaultNotifications: NotificationPrefs = {
  email: true,
  push: true,
  websocket: true,
}

export const defaultPreferences: UserPreferences = {
  default_mode: null,
  smoking: false,
  pets: false,
  notifications: defaultNotifications,
  language: 'en',
  theme: 'system',
}

export const defaultRidePreferences: RidePreferences = {
  smoking: false,
  pets: false,
  music: true,
  gender_only: false,
}

export interface RideRow {
  id: number
  driver_id: number
  start_lat: number
  start_lng: number
  start_address: string
  end_lat: number
  end_lng: number
  end_address: string
  departure_time: string
  capacity: number
  available_seats: number
  price_per_seat: string
  status: RideStatus
  preferences: RidePreferences
  notes: string | null
  created_at: string
  updated_at: string
}

export interface RequestRow {
  id: number
  ride_id: number
  passenger_id: number
  seats_requested: number
  status: RequestStatus
  requested_at: string
  responded_at: string | null
}

export interface RatingRow {
  id: number
  ride_id: number
  from_user_id: number
  to_user_id: number
  role_rated: RoleRated
  score: number
  comment: string | null
  tags: string[]
  created_at: string
}

export interface NotificationRow {
  id: number
  recipient_id: number
  type: NotificationType
  title: string
  message: string
  related_entity_type: 'ride' | 'ride_request' | null
  related_entity_id: number | null
  is_read: boolean
  created_at: string
}

export interface MockDb {
  /** null until onboarding completes, which is what drives ONBOARDING_REQUIRED. */
  me: UserMe | null
  users: UserMe[]
  rides: RideRow[]
  requests: RequestRow[]
  notifications: NotificationRow[]
  ratings: RatingRow[]
  nextRideId: number
  nextRequestId: number
  nextNotificationId: number
  nextRatingId: number
}

function hoursFromNow(hours: number): string {
  return new Date(Date.now() + hours * 3_600_000).toISOString()
}

function seed(): MockDb {
  const driver: UserMe = {
    id: 2,
    email: 'noa@example.com',
    name: 'Noa Berman',
    date_of_birth: '1994-04-18',
    gender: 'female',
    is_admin: false,
    is_active: true,
    driver_rating: 4.8,
    driver_rating_count: 37,
    passenger_rating: null,
    passenger_rating_count: 0,
    preferences: { ...defaultPreferences, default_mode: 'driver' },
    vehicle: { make: 'Toyota', model: 'Corolla', color: 'White', plate: '12-345-67' },
    created_at: '2025-11-02T08:14:00Z',
    last_login_at: '2026-09-30T06:40:00Z',
  }
  const passenger: UserMe = {
    id: 3,
    email: 'omer@example.com',
    name: 'Omer Katz',
    date_of_birth: '1999-07-03',
    gender: 'male',
    is_admin: false,
    is_active: true,
    driver_rating: null,
    driver_rating_count: 0,
    passenger_rating: 4.6,
    passenger_rating_count: 11,
    preferences: { ...defaultPreferences, default_mode: 'passenger' },
    vehicle: null,
    created_at: '2026-03-14T09:00:00Z',
    last_login_at: '2026-09-29T17:20:00Z',
  }

  // One ride by someone else, so a passenger has something to ask for in the
  // browser before any ride of their own exists.
  const rides: RideRow[] = [
    {
      id: 101,
      driver_id: 2,
      start_lat: 32.0853,
      start_lng: 34.7818,
      start_address: 'Rothschild Boulevard 1, Tel Aviv-Yafo, Israel',
      end_lat: 31.7683,
      end_lng: 35.2137,
      end_address: 'Jaffa Street 97, Jerusalem, Israel',
      departure_time: hoursFromNow(28),
      capacity: 3,
      available_seats: 3,
      price_per_seat: '25.00',
      status: 'upcoming',
      preferences: { smoking: false, pets: true, music: true, gender_only: false },
      notes: 'Leaving from the Habima side. One bag each, please.',
      created_at: hoursFromNow(-20),
      updated_at: hoursFromNow(-20),
    },
  ]

  return {
    me: null,
    users: [driver, passenger],
    rides,
    requests: [],
    notifications: [],
    ratings: [],
    nextRideId: 102,
    nextRequestId: 1,
    nextNotificationId: 1,
    nextRatingId: 1,
  }
}

export let db: MockDb = seed()

export function resetMockDb(): void {
  db = seed()
}

/** Signs the mock session in as an already-onboarded user. */
export function seedOnboardedMe(overrides: Partial<UserMe> = {}): UserMe {
  const me: UserMe = {
    id: 1,
    email: 'dvir@example.com',
    name: 'Dvir Levi',
    date_of_birth: '1996-02-11',
    gender: null,
    is_admin: false,
    is_active: true,
    driver_rating: null,
    driver_rating_count: 0,
    passenger_rating: null,
    passenger_rating_count: 0,
    preferences: { ...defaultPreferences },
    vehicle: null,
    created_at: '2026-09-01T10:00:00Z',
    last_login_at: null,
    ...overrides,
  }
  db.me = me
  return me
}

/** A driver with a car, which is what offering a ride requires (CONTRACT §4). */
export function seedOnboardedDriver(overrides: Partial<UserMe> = {}): UserMe {
  return seedOnboardedMe({
    vehicle: { make: 'Mazda', model: '3', color: 'Grey', plate: '88-123-45' },
    preferences: { ...defaultPreferences, default_mode: 'driver' },
    ...overrides,
  })
}

/** `is_admin` lives in our DB, not Clerk (CONTRACT §2 D12) — the mock flag is enough. */
export function seedOnboardedAdmin(overrides: Partial<UserMe> = {}): UserMe {
  return seedOnboardedMe({ is_admin: true, ...overrides })
}

export function findUser(id: number): UserMe | undefined {
  return [db.me, ...db.users].find((candidate) => candidate?.id === id) ?? undefined
}

export function seedRide(overrides: Partial<RideRow> = {}): RideRow {
  const id = overrides.id ?? db.nextRideId++
  const row: RideRow = {
    id,
    driver_id: 2,
    start_lat: 32.0853,
    start_lng: 34.7818,
    start_address: 'Dizengoff Street 50, Tel Aviv-Yafo, Israel',
    end_lat: 32.794,
    end_lng: 34.9896,
    end_address: 'Herzl Street 12, Haifa, Israel',
    departure_time: hoursFromNow(12),
    capacity: 3,
    available_seats: 3,
    price_per_seat: '18.00',
    status: 'upcoming',
    preferences: { ...defaultRidePreferences },
    notes: null,
    created_at: hoursFromNow(-2),
    updated_at: hoursFromNow(-2),
    ...overrides,
  }
  db.rides.push(row)
  return row
}

export function seedRequest(overrides: Partial<RequestRow> = {}): RequestRow {
  const row: RequestRow = {
    id: overrides.id ?? db.nextRequestId++,
    ride_id: 101,
    passenger_id: 3,
    seats_requested: 1,
    status: 'pending',
    requested_at: hoursFromNow(-1),
    responded_at: null,
    ...overrides,
  }
  db.requests.push(row)
  return row
}

export function seedNotification(overrides: Partial<NotificationRow> = {}): NotificationRow {
  const row: NotificationRow = {
    id: overrides.id ?? db.nextNotificationId++,
    recipient_id: db.me?.id ?? 1,
    type: 'request_created',
    title: 'New request',
    message: 'Someone asked for a seat on your ride.',
    related_entity_type: null,
    related_entity_id: null,
    is_read: false,
    created_at: hoursFromNow(0),
    ...overrides,
  }
  db.notifications.push(row)
  return row
}

export function seedRating(overrides: Partial<RatingRow> = {}): RatingRow {
  const row: RatingRow = {
    id: overrides.id ?? db.nextRatingId++,
    ride_id: 101,
    from_user_id: 3,
    to_user_id: 2,
    role_rated: 'driver',
    score: 5,
    comment: null,
    tags: [],
    created_at: hoursFromNow(0),
    ...overrides,
  }
  db.ratings.push(row)
  return row
}

/** The `Notification` wire shape (CONTRACT openapi): no `recipient_id`. */
export function toNotification(row: NotificationRow): Notification {
  return {
    id: row.id,
    type: row.type,
    title: row.title,
    message: row.message,
    related_entity_type: row.related_entity_type,
    related_entity_id: row.related_entity_id,
    is_read: row.is_read,
    created_at: row.created_at,
  }
}

/** Seats taken by approved requests — the invariant behind `available_seats`. */
export function approvedSeats(rideId: number): number {
  return db.requests
    .filter((row) => row.ride_id === rideId && row.status === 'approved')
    .reduce((total, row) => total + row.seats_requested, 0)
}
