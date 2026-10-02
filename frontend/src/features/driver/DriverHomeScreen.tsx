import { Link } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useIncomingRequests } from '../../api/hooks/requests'
import { useMyRides } from '../../api/hooks/rides'
import { useMyStats } from '../../api/hooks/users'
import { useCurrentUser } from '../../auth/currentUserContext'
import { ButtonLink } from '../../components/Button'
import { RideCard } from '../../components/RideCard'
import { StatsGrid } from '../../components/StatsGrid'
import { RideStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { paths } from '../../routes'
import { RatingPrompt } from '../ratings/RatingPrompt'
import { VehicleNeededNotice } from './MyRidesScreen'

/** Quick counters — the full breakdown lives on Profile. */
function HomeStats() {
  const stats = useMyStats()
  if (!stats.data) return null
  const { as_driver } = stats.data
  return (
    <div className="mb-6">
      <StatsGrid
        items={[
          { label: 'Upcoming', value: as_driver.upcoming_rides },
          { label: 'Completed', value: as_driver.rides_completed },
          { label: 'Passengers carried', value: as_driver.passengers_carried },
        ]}
      />
    </div>
  )
}

const PLANNED = ['upcoming', 'full', 'in_progress'] as const

export function DriverHomeScreen() {
  const me = useCurrentUser()
  const rides = useMyRides(PLANNED)
  const waiting = useIncomingRequests('pending')

  const next = rides.data?.[0]
  const rest = rides.data?.slice(1) ?? []
  const pending = waiting.data?.length ?? 0

  return (
    <>
      <TabHeader
        title={`Driving, ${me.name.split(' ')[0]}`}
        lead="Your routes, the seats still free on them, and anyone waiting on your answer."
      />

      <HomeStats />
      <RatingPrompt />

      {pending > 0 ? (
        <Link
          to={paths.driverRequests}
          className="mb-5 block rounded-card border border-signal-deep/40 bg-signal/15 p-4 transition-colors hover:border-signal-deep"
        >
          <p className="text-sm font-semibold">
            {pending === 1 ? 'Someone wants a seat' : `${pending} people want a seat`}
          </p>
          <p className="mt-0.5 text-sm text-ink-70">
            They are waiting on your answer. Open the Requests tab.
          </p>
        </Link>
      ) : null}

      {me.vehicle ? (
        <div className="mb-6">
          <ButtonLink to={paths.createRide}>Offer a ride</ButtonLink>
        </div>
      ) : (
        <div className="mb-6">
          <VehicleNeededNotice />
        </div>
      )}

      {rides.isPending ? <InlineLoader label="Loading your rides" /> : null}

      {rides.isError ? (
        <LoadFailure
          title="Your rides did not load"
          message={messageFor(rides.error)}
          onRetry={() => void rides.refetch()}
        />
      ) : null}

      {rides.data && rides.data.length === 0 ? (
        <EmptyState
          title="Your board is empty"
          body="Post a route you are already driving and passengers heading the same way can ask for a seat."
        />
      ) : null}

      {next ? (
        <section>
          <h2 className="mb-3 text-lg">Next out</h2>
          <RideCard
            ride={next}
            to={paths.driverRide(next.id)}
            badge={<RideStatusPill status={next.status} />}
          />
        </section>
      ) : null}

      {rest.length > 0 ? (
        <section className="mt-7">
          <h2 className="mb-3 text-lg">After that</h2>
          <div className="flex flex-col gap-3">
            {rest.map((ride) => (
              <RideCard
                key={ride.id}
                ride={ride}
                to={paths.driverRide(ride.id)}
                badge={<RideStatusPill status={ride.status} />}
              />
            ))}
          </div>
        </section>
      ) : null}
    </>
  )
}
