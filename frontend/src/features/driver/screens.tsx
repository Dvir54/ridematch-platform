import { useCurrentUser } from '../../auth/currentUserContext'
import { EmptyState } from '../../components/states'
import { TabHeader } from '../../components/TabHeader'

export function DriverHomeScreen() {
  const user = useCurrentUser()
  return (
    <>
      <TabHeader
        title={`Driving, ${user.name.split(' ')[0]}`}
        lead="Your routes, the seats still free on them, and anyone waiting on your answer."
      />
      <EmptyState
        title="Your board is empty"
        body="Post a route you are already driving and passengers heading the same way can ask for a seat."
      />
    </>
  )
}

export function MyRidesScreen() {
  return (
    <>
      <TabHeader title="My rides" />
      <EmptyState
        title="No rides posted yet"
        body="Every route you offer stays here until it is completed or cancelled, with its seat count and its passengers."
      />
    </>
  )
}

export function IncomingRequestsScreen() {
  return (
    <>
      <TabHeader title="Requests" lead="Passengers asking for a seat on one of your rides." />
      <EmptyState
        title="Nobody has asked for a seat"
        body="When someone requests one of your rides, it lands here and you approve or decline it."
      />
    </>
  )
}
