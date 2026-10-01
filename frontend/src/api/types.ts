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
export type Vehicle = Schemas['Vehicle']
export type OnboardingRequest = Schemas['OnboardingRequest']

export type Ride = Schemas['Ride']
export type RideRequest = Schemas['RideRequest']
export type Notification = Schemas['Notification']

/**
 * PATCH /users/me shallow-merges preferences (CONTRACT §4), so a partial object
 * is valid on the wire. The generated `UserPreferences` marks every key with a
 * schema default as required, which is right for reads but not for this patch.
 */
export type UserPreferencesPatch = Partial<Omit<UserPreferences, 'notifications'>> & {
  notifications?: Partial<NotificationPrefs>
}

export type UserPatch = Omit<UserUpdate, 'preferences'> & {
  preferences?: UserPreferencesPatch
}
