import { Link, Navigate } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useCancelRide, useCompleteRide, useStartRide } from '../../api/hooks/rides'
import { useRideRequests } from '../../api/hooks/requests'
import type { Ride, RideRequest } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { Button, ButtonLink } from '../../components/Button'
import { ConfirmAction } from '../../components/ConfirmAction'
import { PersonLine } from '../../components/PersonLine'
import { RequestStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { ErrorNotice, InlineLoader, LoadFailure, MessageScreen } from '../../components/states'
import { canStartYet, formatDateTime } from '../../lib/dates'
import { paths } from '../../routes'
import { RideFacts } from '../rides/RideFacts'
import { useRouteRide } from '../rides/useRouteRide'
import { RequestActions } from './RequestActions'

/** What a driver may do from here, as CONTRACT §3 allows it. */
function RideActions({ ride }: { ride: Ride }) {
  const cancel = useCancelRide(ride.id)
  const start = useStartRide(ride.id)
  const complete = useCompleteRide(ride.id)
  const failure = cancel.error ?? start.error ?? complete.error

  const open = ride.status === 'upcoming' || ride.status === 'full'
  const startable = canStartYet(ride.departure_time)

  if (ride.status === 'completed' || ride.status === 'cancelled') {
    return (
      <p className="text-sm text-ink-70">
        This ride is {ride.status}. Nothing left to do here.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {failure ? <ErrorNotice>{messageFor(failure)}</ErrorNotice> : null}

      {ride.status === 'in_progress' ? (
        <>
          <Button disabled={complete.isPending} onClick={() => complete.mutate()}>
            {complete.isPending ? 'Finishing…' : 'Finish the ride'}
          </Button>
          <p className="text-sm text-ink-70">
            Finishing opens ratings for you and everyone who rode with you.
          </p>
        </>
      ) : null}

      {open ? (
        <>
          <Button disabled={!startable || start.isPending} onClick={() => start.mutate()}>
            {start.isPending ? 'Starting…' : 'Start the ride'}
          </Button>
          <p className="text-sm text-ink-70">
            {startable
              ? 'Starting it declines anyone still waiting for an answer.'
              : `You can start from two hours before departure — ${formatDateTime(ride.departure_time)}.`}
          </p>
          <div className="flex flex-wrap items-start gap-2">
            <ButtonLink to={paths.editRide(ride.id)} variant="secondary">
              Edit
            </ButtonLink>
            <ConfirmAction
              label="Cancel the ride"
              question="Everyone who asked for or got a seat will be told the ride is off."
              confirmLabel="Cancel the ride"
              pending={cancel.isPending}
              onConfirm={() => cancel.mutate()}
            />
          </div>
        </>
      ) : null}
    </div>
  )
}

function PassengerRow({ request }: { request: RideRequest }) {
  return (
    <li className="rounded-card border border-hairline bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <PersonLine person={request.passenger} role="passenger" />
        <RequestStatusPill status={request.status} />
      </div>
      <p className="tnum mt-1 text-sm text-ink-70">
        {request.seats_requested === 1 ? '1 seat' : `${request.seats_requested} seats`} · asked{' '}
        {formatDateTime(request.requested_at)}
      </p>
      <RequestActions request={request} />
    </li>
  )
}

function PassengerList({ rideId }: { rideId: number }) {
  const requests = useRideRequests(rideId)

  if (requests.isPending) return <InlineLoader label="Loading the people on this ride" />
  if (requests.isError) {
    return (
      <LoadFailure
        title="The passenger list did not load"
        message={messageFor(requests.error)}
        onRetry={() => void requests.refetch()}
      />
    )
  }

  const rows = requests.data
  const waiting = rows.filter((row) => row.status === 'pending')
  const aboard = rows.filter((row) => row.status === 'approved')
  const closed = rows.filter((row) => row.status === 'rejected' || row.status === 'cancelled')

  if (rows.length === 0) {
    return (
      <p className="text-sm text-ink-70">
        Nobody has asked for a seat yet. Requests land here and in the Requests tab.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {waiting.length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold">
            Waiting on you ({waiting.length})
          </h3>
          <ul className="flex flex-col gap-3">
            {waiting.map((row) => (
              <PassengerRow key={row.id} request={row} />
            ))}
          </ul>
        </section>
      ) : null}

      {aboard.length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Coming along ({aboard.length})</h3>
          <ul className="flex flex-col gap-3">
            {aboard.map((row) => (
              <PassengerRow key={row.id} request={row} />
            ))}
          </ul>
        </section>
      ) : null}

      {closed.length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink-45">Not riding ({closed.length})</h3>
          <ul className="flex flex-col gap-3">
            {closed.map((row) => (
              <PassengerRow key={row.id} request={row} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

export function DriverRideScreen() {
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
  // Arriving at the driver's half of a ride you do not drive: show the passenger
  // half instead, which is the screen that can actually do something.
  if (ride.driver.id !== me.id) return <Navigate to={paths.passengerRide(ride.id)} replace />

  return (
    <>
      <TabHeader title="Your ride" />
      <Link
        to={paths.driverRides}
        className="mb-4 inline-block text-sm font-semibold text-ink-70 underline decoration-ink/30 underline-offset-4 hover:text-ink"
      >
        All my rides
      </Link>

      <div className="flex flex-col gap-6">
        <RideFacts ride={ride} />

        <section>
          <h2 className="mb-3 text-lg">What now</h2>
          <RideActions ride={ride} />
        </section>

        <section>
          <h2 className="mb-3 text-lg">Passengers</h2>
          <PassengerList rideId={ride.id} />
        </section>
      </div>
    </>
  )
}
