/**
 * Named aliases over the types generated from contracts/openapi.yaml.
 * Never hand-write an API shape here — re-run `npm run gen:api` instead.
 */
import type { components } from './schema'

export type Schemas = components['schemas']

export type ApiErrorBody = Schemas['Error']
export type FieldError = NonNullable<ApiErrorBody['details']>[number]

export type Gender = Schemas['Gender']
export type Mode = Schemas['Mode']
export type Money = Schemas['Money']
export type RideStatus = Schemas['RideStatus']
export type RequestStatus = Schemas['RequestStatus']
export type NotificationType = Schemas['NotificationType']

export type UserMe = Schemas['UserMe']
export type UserPublic = Schemas['UserPublic']
export type UserUpdate = Schemas['UserUpdate']
export type UserStats = Schemas['UserStats']
export type UserPreferences = Schemas['UserPreferences']
export type NotificationPrefs = Schemas['NotificationPrefs']
/** The write shape: every key optional, because PATCH shallow-merges (CONTRACT §4). */
export type UserPreferencesPatch = Schemas['UserPreferencesPatch']
export type Vehicle = Schemas['Vehicle']
export type OnboardingRequest = Schemas['OnboardingRequest']

export type Ride = Schemas['Ride']
export type RideRequest = Schemas['RideRequest']
export type Notification = Schemas['Notification']
