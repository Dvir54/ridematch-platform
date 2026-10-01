import { useState } from 'react'
import { messageFor } from '../../api/errors'
import { useMyRequests } from '../../api/hooks/requests'
import type { RequestStatus } from '../../api/types'
import { RideCard } from '../../components/RideCard'
import { RequestStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { paths } from '../../routes'
import { CancelRequestAction } from './CancelRequestAction'

const FILTERS: { id: string; label: string; statuses?: RequestStatus[] }[] = [
  { id: 'active', label: 'Active', statuses: ['pending', 'approved'] },
  { id: 'past', label: 'Past', statuses: ['rejected', 'cancelled'] },
  { id: 'all', label: 'All' },
]

export function MyTripsScreen() {
  const [filterId, setFilterId] = useState('active')
  const filter = FILTERS.find((candidate) => candidate.id === filterId) ?? FILTERS[0]
  const requests = useMyRequests(filter.statuses)

  return (
    <>
      <TabHeader
        title="My trips"
        lead="Every seat you have asked for — waiting, confirmed or closed."
      />

      <div role="group" aria-label="Filter trips" className="mb-5 flex gap-2">
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

      {requests.isPending ? <InlineLoader label="Loading your trips" /> : null}

      {requests.isError ? (
        <LoadFailure
          title="Your trips did not load"
          message={messageFor(requests.error)}
          onRetry={() => void requests.refetch()}
        />
      ) : null}

      {requests.data?.length === 0 ? (
        <EmptyState
          title={filterId === 'past' ? 'Nothing closed yet' : 'No trips yet'}
          body={
            filterId === 'past'
              ? 'Requests that were declined or that you withdrew end up here.'
              : 'Open a ride and ask for a seat. It appears here the moment you do.'
          }
        />
      ) : null}

      <div className="flex flex-col gap-4">
        {requests.data?.map((request) => (
          <div key={request.id} className="flex flex-col gap-3">
            <RideCard
              ride={request.ride}
              to={paths.passengerRide(request.ride.id)}
              badge={<RequestStatusPill status={request.status} />}
              footer={
                <p className="tnum mt-1 text-sm text-ink-70">
                  {request.seats_requested === 1
                    ? '1 seat'
                    : `${request.seats_requested} seats`}{' '}
                  · {request.ride.driver.name} driving
                </p>
              }
            />
            <CancelRequestAction request={request} />
          </div>
        ))}
      </div>
    </>
  )
}
