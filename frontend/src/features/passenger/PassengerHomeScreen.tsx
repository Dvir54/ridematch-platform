import { messageFor } from '../../api/errors'
import { useMyRequests } from '../../api/hooks/requests'
import { useMyStats } from '../../api/hooks/users'
import { useCurrentUser } from '../../auth/currentUserContext'
import { ButtonLink } from '../../components/Button'
import { RideCard } from '../../components/RideCard'
import { StatsGrid } from '../../components/StatsGrid'
import { RequestStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { paths } from '../../routes'
import { RatingPrompt } from '../ratings/RatingPrompt'

const ACTIVE = ['pending', 'approved'] as const

/** Quick counters — the full breakdown lives on Profile. */
function HomeStats() {
  const stats = useMyStats()
  if (!stats.data) return null
  const { as_passenger } = stats.data
  return (
    <div className="mb-6">
      <StatsGrid
        items={[
          { label: 'Upcoming', value: as_passenger.upcoming_trips },
          { label: 'Completed', value: as_passenger.trips_completed },
          { label: 'Requested', value: as_passenger.trips_requested },
        ]}
      />
    </div>
  )
}

export function PassengerHomeScreen() {
  const me = useCurrentUser()
  const requests = useMyRequests(ACTIVE)

  // /requests/mine is newest first; a passenger cares about the soonest departure.
  const soonest = [...(requests.data ?? [])].sort((a, b) =>
    a.ride.departure_time.localeCompare(b.ride.departure_time),
  )
  const waiting = soonest.filter((request) => request.status === 'pending').length

  return (
    <>
      <TabHeader
        title={`Riding, ${me.name.split(' ')[0]}`}
        lead="The seats you asked for, and the ones a driver has already confirmed."
      />

      <div className="mb-6">
        <ButtonLink to={paths.passengerSearch}>Find a ride</ButtonLink>
      </div>

      <HomeStats />
      <RatingPrompt />

      {waiting > 0 ? (
        <p className="mb-5 text-sm text-ink-70">
          {waiting === 1
            ? 'One request is still waiting on a driver.'
            : `${waiting} requests are still waiting on a driver.`}
        </p>
      ) : null}

      {requests.isPending ? <InlineLoader label="Loading your trips" /> : null}

      {requests.isError ? (
        <LoadFailure
          title="Your trips did not load"
          message={messageFor(requests.error)}
          onRetry={() => void requests.refetch()}
        />
      ) : null}

      {requests.data && requests.data.length === 0 ? (
        <EmptyState
          title="Nothing booked"
          body="Search for a driver going your way, ask for a seat, and the trip appears here as soon as it is confirmed."
        />
      ) : null}

      <div className="flex flex-col gap-3">
        {soonest.map((request) => (
          <RideCard
            key={request.id}
            ride={request.ride}
            to={paths.passengerRide(request.ride.id)}
            badge={<RequestStatusPill status={request.status} />}
            footer={
              <p className="mt-1 text-sm text-ink-70">{request.ride.driver.name} driving</p>
            }
          />
        ))}
      </div>
    </>
  )
}
