import { useCurrentUser } from '../../auth/currentUserContext'
import { EmptyState } from '../../components/states'
import { TabHeader } from '../../components/TabHeader'

export function PassengerHomeScreen() {
  const user = useCurrentUser()
  return (
    <>
      <TabHeader
        title={`Riding, ${user.name.split(' ')[0]}`}
        lead="The seats you asked for, and the ones a driver has already confirmed."
      />
      <EmptyState
        title="Nothing booked"
        body="Search for a driver going your way, ask for a seat, and the trip appears here as soon as it is confirmed."
      />
    </>
  )
}

export function SearchScreen() {
  return (
    <>
      <TabHeader title="Search" />
      <EmptyState
        title="Route search is being built"
        body="You will give a pickup point, a destination and a time. RideMatch scores every driver heading the same way and ranks them."
      />
    </>
  )
}

export function MyTripsScreen() {
  return (
    <>
      <TabHeader title="My trips" />
      <EmptyState
        title="No trips yet"
        body="Requests you send stay here — waiting, confirmed or declined — along with the rides you have taken."
      />
    </>
  )
}
