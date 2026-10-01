import type { NotificationPrefs, UserMe, UserPreferences } from '../api/types'

/**
 * A tiny in-memory stand-in for the backend, shaped exactly like
 * contracts/openapi.yaml. It exists so screens can be built and tested before
 * @backend ships an endpoint — not as a second source of truth.
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

export interface MockDb {
  /** null until onboarding completes, which is what drives ONBOARDING_REQUIRED. */
  me: UserMe | null
  users: UserMe[]
}

function seed(): MockDb {
  const driver: UserMe = {
    id: 2,
    email: 'noa@example.com',
    name: 'Noa Berman',
    phone: '+972 52 555 0101',
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
  return { me: null, users: [driver] }
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
    phone: null,
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
