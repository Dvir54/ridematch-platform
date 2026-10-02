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
export type VehiclePublic = Schemas['VehiclePublic']
export type OnboardingRequest = Schemas['OnboardingRequest']

export type Ride = Schemas['Ride']
export type RideCreate = Schemas['RideCreate']
export type RideUpdate = Schemas['RideUpdate']
export type RidePreferences = Schemas['RidePreferences']
/** Ride preferences shallow-merge on PATCH too, so writes carry no defaults (D16). */
export type RidePreferencesPatch = Schemas['RidePreferencesPatch']

export type RideRequest = Schemas['RideRequest']
export type RideRequestCreate = Schemas['RideRequestCreate']
/** The caller's own blocking request on a ride, carried by `Ride.my_request` (D20). */
export type MyRequest = Schemas['MyRequest']

export type ScoreBreakdown = Schemas['ScoreBreakdown']
export type RideMatch = Schemas['RideMatch']
/** The `/search` sort parameter — an inline enum in openapi.yaml, not a named schema. */
export type SearchSort = 'best_match' | 'earliest' | 'cheapest'

export type Notification = Schemas['Notification']

export type RoleRated = Schemas['RoleRated']
export type Rating = Schemas['Rating']
export type RatingCreate = Schemas['RatingCreate']
export type PendingRating = Schemas['PendingRating']

export type AdminUserDetail = Schemas['AdminUserDetail']
export type AnalyticsSummary = Schemas['AnalyticsSummary']
