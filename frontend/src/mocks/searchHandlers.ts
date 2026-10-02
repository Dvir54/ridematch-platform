import { http, HttpResponse } from 'msw'
import { env } from '../env'
import type { RideMatch, SearchSort } from '../api/types'
import { db, findUser } from './db'
import type { RideRow } from './db'
import { onboardingRequired, paginate, signedIn, unauthenticated } from './http'
import { toRide } from './project'

const base = env.apiBaseUrl.replace(/\/$/, '')

/** CONTRACT §7: the matching formula's two constants. */
const SEARCH_RADIUS_KM = 10
const MATCH_MIN_SCORE = 40
const EARTH_RADIUS_KM = 6371
const HOUR_MS = 3_600_000

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

interface Query {
  start_lat: number
  start_lng: number
  end_lat: number
  end_lng: number
  time: string
  budget?: string
  seats: number
  sort: SearchSort
}

function routeScore(p: number, d: number): number {
  return 20 * Math.max(0, 1 - p / SEARCH_RADIUS_KM) + 20 * Math.max(0, 1 - d / SEARCH_RADIUS_KM)
}

function timeScore(deltaHours: number): number {
  if (deltaHours <= 2) return 25
  if (deltaHours <= 4) return 25 * ((4 - deltaHours) / 2)
  return 0
}

function priceScore(price: number, budget: number | undefined): number {
  if (budget === undefined || price <= budget) return 15
  if (budget === 0) return 0
  return 15 * Math.max(0, 1 - (price - budget) / budget)
}

function ratingScore(rating: number | null): number {
  if (rating === null) return 5
  if (rating >= 4.5) return 10
  return (10 * (rating - 1)) / 3.5
}

function preferencesScore(
  ride: RideRow,
  passengerSmoking: boolean,
  passengerPets: boolean,
): number {
  let score = 10
  if (ride.preferences.smoking && !passengerSmoking) score -= 5
  if (ride.preferences.pets && !passengerPets) score -= 5
  return Math.max(0, score)
}

export const searchHandlers = [
  http.get(`${base}/search`, ({ request }) => {
    if (!signedIn(request)) return unauthenticated()
    if (!db.me) return onboardingRequired()
    const me = db.me

    const url = new URL(request.url)
    const q: Query = {
      start_lat: Number(url.searchParams.get('start_lat')),
      start_lng: Number(url.searchParams.get('start_lng')),
      end_lat: Number(url.searchParams.get('end_lat')),
      end_lng: Number(url.searchParams.get('end_lng')),
      time: url.searchParams.get('time') ?? '',
      budget: url.searchParams.get('budget') ?? undefined,
      seats: Number(url.searchParams.get('seats') ?? 1),
      sort: (url.searchParams.get('sort') as SearchSort | null) ?? 'best_match',
    }
    const wantedTime = new Date(q.time).getTime()
    const budget = q.budget !== undefined ? Number(q.budget) : undefined

    const myActiveRideIds = new Set(
      db.requests
        .filter(
          (row) =>
            row.passenger_id === me.id && (row.status === 'pending' || row.status === 'approved'),
        )
        .map((row) => row.ride_id),
    )

    const matches: RideMatch[] = []

    for (const row of db.rides) {
      if (row.status !== 'upcoming') continue
      if (row.available_seats < q.seats) continue
      if (row.driver_id === me.id) continue
      if (myActiveRideIds.has(row.id)) continue
      if (new Date(row.departure_time).getTime() <= Date.now()) continue

      const deltaHours = Math.abs(new Date(row.departure_time).getTime() - wantedTime) / HOUR_MS
      if (deltaHours > 4) continue

      if (row.preferences.gender_only) {
        if (!me.gender) continue
        const driver = findUser(row.driver_id)
        if (!driver?.gender || driver.gender !== me.gender) continue
      }

      const p = haversine(q.start_lat, q.start_lng, row.start_lat, row.start_lng)
      const d = haversine(q.end_lat, q.end_lng, row.end_lat, row.end_lng)
      if (p > SEARCH_RADIUS_KM || d > SEARCH_RADIUS_KM) continue

      const driver = findUser(row.driver_id)
      const score =
        routeScore(p, d) +
        timeScore(deltaHours) +
        priceScore(Number(row.price_per_seat), budget) +
        ratingScore(driver?.driver_rating ?? null) +
        preferencesScore(row, me.preferences.smoking, me.preferences.pets)
      const rounded = Math.round(score * 10) / 10

      if (rounded < MATCH_MIN_SCORE) continue

      matches.push({
        ride: toRide(row, me.id),
        match_score: rounded,
        breakdown: {
          route: Math.round(routeScore(p, d) * 10) / 10,
          time: Math.round(timeScore(deltaHours) * 10) / 10,
          price: Math.round(priceScore(Number(row.price_per_seat), budget) * 10) / 10,
          rating: Math.round(ratingScore(driver?.driver_rating ?? null) * 10) / 10,
          preferences: preferencesScore(row, me.preferences.smoking, me.preferences.pets),
        },
        pickup_distance_km: Math.round(p * 100) / 100,
        dropoff_distance_km: Math.round(d * 100) / 100,
      })
    }

    matches.sort((a, b) => {
      if (q.sort === 'earliest') {
        return a.ride.departure_time.localeCompare(b.ride.departure_time)
      }
      if (q.sort === 'cheapest') {
        const priceDiff = Number(a.ride.price_per_seat) - Number(b.ride.price_per_seat)
        return priceDiff !== 0 ? priceDiff : b.match_score - a.match_score
      }
      const scoreDiff = b.match_score - a.match_score
      return scoreDiff !== 0 ? scoreDiff : a.ride.departure_time.localeCompare(b.ride.departure_time)
    })

    return HttpResponse.json(paginate(matches, url))
  }),
]
