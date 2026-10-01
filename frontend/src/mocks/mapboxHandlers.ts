import { http, HttpResponse } from 'msw'
import { MAPBOX_FORWARD_URL } from '../lib/mapbox'

/**
 * Stand-in for Mapbox Geocoding v6. Address autocomplete is the one place the
 * frontend talks to a third party (scope G5a), so it gets a mock like every
 * other call — otherwise the ride forms could not be built or tested offline.
 *
 * Each answer is derived from the query, so a test can type a street name and
 * then assert on the coordinates that came back with it.
 */
const PLACES = [
  { town: 'Tel Aviv-Yafo', lat: 32.0853, lng: 34.7818 },
  { town: 'Jerusalem', lat: 31.7683, lng: 35.2137 },
  { town: 'Haifa', lat: 32.794, lng: 34.9896 },
]

export const mapboxHandlers = [
  http.get(MAPBOX_FORWARD_URL, ({ request }) => {
    const url = new URL(request.url)
    const query = (url.searchParams.get('q') ?? '').trim()
    const limit = Math.min(Number(url.searchParams.get('limit') ?? 5) || 5, PLACES.length)
    if (!query) return HttpResponse.json({ type: 'FeatureCollection', features: [] })

    return HttpResponse.json({
      type: 'FeatureCollection',
      features: PLACES.slice(0, limit).map((place, index) => ({
        type: 'Feature',
        id: `mock.${index}`,
        geometry: { type: 'Point', coordinates: [place.lng, place.lat] },
        properties: {
          mapbox_id: `mock.${index}`,
          feature_type: 'address',
          name: query,
          full_address: `${query}, ${place.town}, Israel`,
          place_formatted: `${place.town}, Israel`,
          coordinates: { latitude: place.lat, longitude: place.lng },
        },
      })),
    })
  }),
]
