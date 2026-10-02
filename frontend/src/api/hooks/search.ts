import { useQuery } from '@tanstack/react-query'
import { api } from '../client'
import type { SearchParams } from '../keys'
import { searchKeys } from '../keys'
import type { RideMatch } from '../types'

/** `/search` (CONTRACT §7). Disabled until a route and time are chosen. */
export function useSearchRides(params: SearchParams | null) {
  return useQuery({
    queryKey: searchKeys.results(params ?? ({} as SearchParams)),
    queryFn: ({ signal }) =>
      api.get<RideMatch[]>(
        '/search',
        {
          start_lat: params!.start_lat,
          start_lng: params!.start_lng,
          end_lat: params!.end_lat,
          end_lng: params!.end_lng,
          time: params!.time,
          budget: params!.budget,
          seats: params!.seats,
          sort: params!.sort,
        },
        signal,
      ),
    enabled: params !== null,
  })
}
