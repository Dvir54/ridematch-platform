import { Navigate, useNavigate } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useUpdateRide } from '../../api/hooks/rides'
import type { Ride } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { ButtonLink } from '../../components/Button'
import { TabHeader } from '../../components/TabHeader'
import { InlineLoader, LoadFailure, MessageScreen } from '../../components/states'
import { paths } from '../../routes'
import { useRouteRide } from '../rides/useRouteRide'
import { RideForm } from './RideForm'

/**
 * Split out so the form mounts with the ride already in hand: its fields are
 * seeded once from the ride, not synced to it on every render.
 */
function EditForm({ ride }: { ride: Ride }) {
  const navigate = useNavigate()
  const updateRide = useUpdateRide(ride.id)

  return (
    <RideForm
      ride={ride}
      submitLabel="Save the changes"
      pending={updateRide.isPending}
      error={updateRide.error}
      onUpdate={(body) =>
        updateRide.mutate(body, {
          onSuccess: () => navigate(paths.driverRide(ride.id), { replace: true }),
        })
      }
      onCancel={() => navigate(paths.driverRide(ride.id))}
    />
  )
}

export function EditRideScreen() {
  const me = useCurrentUser()
  const { rideId, query } = useRouteRide()

  if (rideId === undefined) {
    return (
      <MessageScreen
        title="No such ride"
        body="That link does not point at a ride."
        action={<ButtonLink to={paths.driverRides}>Back to my rides</ButtonLink>}
      />
    )
  }

  if (query.isPending) return <InlineLoader label="Loading the ride" />
  if (query.isError) {
    return (
      <LoadFailure
        title="This ride did not load"
        message={messageFor(query.error)}
        onRetry={() => void query.refetch()}
      />
    )
  }

  const ride = query.data
  if (ride.driver.id !== me.id) return <Navigate to={paths.passengerRide(ride.id)} replace />
  // Only an upcoming or full ride can be edited; anything else is a 409.
  if (ride.status !== 'upcoming' && ride.status !== 'full') {
    return (
      <MessageScreen
        title={`This ride is ${ride.status}`}
        body="A ride can only be edited while it is still ahead of you."
        action={<ButtonLink to={paths.driverRide(ride.id)}>Back to the ride</ButtonLink>}
      />
    )
  }

  return (
    <>
      <TabHeader title="Edit the ride" />
      <EditForm ride={ride} />
    </>
  )
}
