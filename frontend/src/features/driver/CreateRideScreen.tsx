import { useNavigate } from 'react-router-dom'
import { useCreateRide } from '../../api/hooks/rides'
import { useCurrentUser } from '../../auth/currentUserContext'
import { TabHeader } from '../../components/TabHeader'
import { paths } from '../../routes'
import { RideForm } from './RideForm'
import { VehicleNeededNotice } from './MyRidesScreen'

export function CreateRideScreen() {
  const me = useCurrentUser()
  const navigate = useNavigate()
  const createRide = useCreateRide()

  if (!me.vehicle) {
    return (
      <>
        <TabHeader title="Offer a ride" />
        <VehicleNeededNotice />
      </>
    )
  }

  return (
    <>
      <TabHeader
        title="Offer a ride"
        lead="Say where you are going and when. Passengers ask for a seat and you decide."
      />
      <RideForm
        submitLabel="Post the ride"
        pending={createRide.isPending}
        error={createRide.error}
        onCreate={(body) =>
          createRide.mutate(body, {
            onSuccess: (ride) => navigate(paths.driverRide(ride.id), { replace: true }),
          })
        }
        onCancel={() => navigate(paths.driverRides)}
      />
    </>
  )
}
