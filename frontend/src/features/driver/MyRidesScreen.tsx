import { useState } from 'react'
import { messageFor } from '../../api/errors'
import { useMyRides } from '../../api/hooks/rides'
import type { RideStatus } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { ButtonLink } from '../../components/Button'
import { RideCard } from '../../components/RideCard'
import { RideStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { paths } from '../../routes'

const FILTERS: { id: string; label: string; statuses?: RideStatus[] }[] = [
  { id: 'planned', label: 'Planned', statuses: ['upcoming', 'full', 'in_progress'] },
  { id: 'finished', label: 'Finished', statuses: ['completed', 'cancelled'] },
  { id: 'all', label: 'All' },
]

/** Offering a ride needs a car on the profile (CONTRACT §4), so say it up front. */
export function VehicleNeededNotice() {
  return (
    <div className="rounded-card border border-signal-deep/40 bg-signal/15 p-4">
      <p className="text-sm font-semibold">Add your car first</p>
      <p className="mt-1 text-sm text-ink-70">
        Passengers need to know what they are looking for, so RideMatch asks for the make, model,
        colour and plate before you can offer a ride. Only the plate stays private, and only
        approved passengers see it.
      </p>
      <div className="mt-3">
        <ButtonLink to={paths.profile} variant="secondary">
          Add your car
        </ButtonLink>
      </div>
    </div>
  )
}

export function MyRidesScreen() {
  const me = useCurrentUser()
  const [filterId, setFilterId] = useState('planned')
  const filter = FILTERS.find((candidate) => candidate.id === filterId) ?? FILTERS[0]
  const rides = useMyRides(filter.statuses)

  return (
    <>
      <TabHeader title="My rides" lead="Every route you have offered, and where each one stands." />

      {me.vehicle ? (
        <div className="mb-5">
          <ButtonLink to={paths.createRide}>Offer a ride</ButtonLink>
        </div>
      ) : (
        <div className="mb-5">
          <VehicleNeededNotice />
        </div>
      )}

      <div role="group" aria-label="Filter rides" className="mb-5 flex gap-2">
        {FILTERS.map((candidate) => (
          <button
            key={candidate.id}
            type="button"
            aria-pressed={candidate.id === filterId}
            onClick={() => setFilterId(candidate.id)}
            className={`rounded-full border px-3 py-1 text-sm font-semibold ${
              candidate.id === filterId
                ? 'border-ink bg-ink text-surface'
                : 'border-hairline text-ink-70 hover:border-ink hover:text-ink'
            }`}
          >
            {candidate.label}
          </button>
        ))}
      </div>

      {rides.isPending ? <InlineLoader label="Loading your rides" /> : null}

      {rides.isError ? (
        <LoadFailure
          title="Your rides did not load"
          message={messageFor(rides.error)}
          onRetry={() => void rides.refetch()}
        />
      ) : null}

      {rides.data?.length === 0 ? (
        <EmptyState
          title={filterId === 'finished' ? 'Nothing finished yet' : 'No rides here'}
          body={
            filterId === 'finished'
              ? 'Rides you complete or cancel move here, so you keep a record of them.'
              : 'Post a route you are already driving and passengers heading the same way can ask for a seat.'
          }
        />
      ) : null}

      <div className="flex flex-col gap-3">
        {rides.data?.map((ride) => (
          <RideCard
            key={ride.id}
            ride={ride}
            to={paths.driverRide(ride.id)}
            badge={<RideStatusPill status={ride.status} />}
          />
        ))}
      </div>
    </>
  )
}
