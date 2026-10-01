import { Link } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useIncomingRequests } from '../../api/hooks/requests'
import type { RideRequest } from '../../api/types'
import { PersonLine } from '../../components/PersonLine'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { shortAddress } from '../../lib/address'
import { formatDateTime } from '../../lib/dates'
import { paths } from '../../routes'
import { RequestActions } from './RequestActions'

interface Group {
  rideId: number
  departure: string
  route: string
  requests: RideRequest[]
}

/**
 * `/requests/incoming` answers one flat list across every ride, so the screen
 * groups it by ride — a driver decides per ride, not per stranger.
 */
function groupByRide(requests: RideRequest[]): Group[] {
  const groups = new Map<number, Group>()
  for (const request of requests) {
    const existing = groups.get(request.ride.id)
    if (existing) {
      existing.requests.push(request)
      continue
    }
    groups.set(request.ride.id, {
      rideId: request.ride.id,
      departure: request.ride.departure_time,
      route: `${shortAddress(request.ride.start_address)} → ${shortAddress(request.ride.end_address)}`,
      requests: [request],
    })
  }
  return [...groups.values()].sort((a, b) => a.departure.localeCompare(b.departure))
}

export function IncomingRequestsScreen() {
  const requests = useIncomingRequests('pending')

  return (
    <>
      <TabHeader
        title="Requests"
        lead="Everyone waiting on your answer, newest first, grouped by the ride they want."
      />

      {requests.isPending ? <InlineLoader label="Loading requests" /> : null}

      {requests.isError ? (
        <LoadFailure
          title="Requests did not load"
          message={messageFor(requests.error)}
          onRetry={() => void requests.refetch()}
        />
      ) : null}

      {requests.data?.length === 0 ? (
        <EmptyState
          title="Nobody is waiting"
          body="When someone asks for a seat on one of your rides, it lands here and you approve or decline it."
        />
      ) : null}

      <div className="flex flex-col gap-7">
        {requests.data
          ? groupByRide(requests.data).map((group) => (
              <section key={group.rideId}>
                <Link to={paths.driverRide(group.rideId)} className="group block">
                  <p className="tnum text-sm font-semibold group-hover:underline">
                    {formatDateTime(group.departure)}
                  </p>
                  <p className="text-sm text-ink-70">{group.route}</p>
                </Link>

                <ul className="mt-3 flex flex-col gap-3">
                  {group.requests.map((request) => (
                    <li
                      key={request.id}
                      className="rounded-card border border-hairline bg-surface p-4"
                    >
                      <PersonLine person={request.passenger} role="passenger" />
                      <p className="tnum mt-1 text-sm text-ink-70">
                        {request.seats_requested === 1
                          ? '1 seat'
                          : `${request.seats_requested} seats`}{' '}
                        · asked {formatDateTime(request.requested_at)}
                      </p>
                      <RequestActions request={request} />
                    </li>
                  ))}
                </ul>
              </section>
            ))
          : null}
      </div>
    </>
  )
}
