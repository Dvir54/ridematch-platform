import { useParams } from 'react-router-dom'
import { useRide } from '../../api/hooks/rides'

/**
 * The ride named by `:rideId`, shared by the driver and passenger ride screens.
 * A path that is not a number never reaches the API — the query stays disabled
 * and the screen shows its own "no such ride".
 */
export function useRouteRide() {
  const { rideId } = useParams<{ rideId: string }>()
  const id = Number(rideId)
  const valid = Number.isInteger(id) && id > 0

  return { rideId: valid ? id : undefined, query: useRide(valid ? id : undefined) }
}
