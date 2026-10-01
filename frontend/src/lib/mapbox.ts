import { env } from '../env'

/**
 * Address autocomplete is frontend-only (scope G5a): Mapbox turns what the user
 * types into an address plus coordinates, and the ride body carries
 * `*_address` + `*_lat`/`*_lng` exactly as the contract says. The backend never
 * calls Mapbox.
 *
 * This uses the Geocoding v6 forward endpoint, which answers with coordinates
 * in one request — no session token and no second `retrieve` round trip.
 */
export const MAPBOX_FORWARD_URL = 'https://api.mapbox.com/search/geocode/v6/forward'

/** What a ride form needs about a place: the three fields the contract wants. */
export interface AddressValue {
  address: string
  lat: number
  lng: number
}

export interface AddressSuggestion extends AddressValue {
  id: string
  /** The quieter second line — town, region, country. */
  context: string
}

interface ForwardFeature {
  id?: string
  geometry?: { coordinates?: [number, number] }
  properties?: {
    mapbox_id?: string
    name?: string
    full_address?: string
    place_formatted?: string
    coordinates?: { latitude?: number; longitude?: number }
  }
}

function toSuggestion(feature: ForwardFeature, index: number): AddressSuggestion | null {
  const properties = feature.properties ?? {}
  const [lng, lat] = feature.geometry?.coordinates ?? [
    properties.coordinates?.longitude,
    properties.coordinates?.latitude,
  ]
  const address = properties.full_address ?? properties.name
  if (!address || typeof lat !== 'number' || typeof lng !== 'number') return null

  return {
    id: properties.mapbox_id ?? feature.id ?? `${index}`,
    // start_address / end_address cap at 255 characters in openapi.yaml.
    address: address.slice(0, 255),
    context: properties.full_address ? (properties.place_formatted ?? '') : '',
    lat,
    lng,
  }
}

export class MapboxError extends Error {}

/** Up to five places matching `query`. Throws `MapboxError` if Mapbox is unhappy. */
export async function searchAddresses(
  query: string,
  options: { signal?: AbortSignal; limit?: number } = {},
): Promise<AddressSuggestion[]> {
  if (!env.mapboxToken) throw new MapboxError('No Mapbox token is configured.')

  const url = new URL(MAPBOX_FORWARD_URL)
  url.searchParams.set('q', query)
  url.searchParams.set('access_token', env.mapboxToken)
  url.searchParams.set('limit', String(options.limit ?? 5))
  url.searchParams.set('autocomplete', 'true')
  url.searchParams.set('language', navigator.language.slice(0, 2) || 'en')

  const response = await fetch(url, { signal: options.signal })
  if (!response.ok) throw new MapboxError(`Mapbox answered ${response.status}.`)

  const body = (await response.json()) as { features?: ForwardFeature[] }
  return (body.features ?? [])
    .map(toSuggestion)
    .filter((suggestion): suggestion is AddressSuggestion => suggestion !== null)
}
