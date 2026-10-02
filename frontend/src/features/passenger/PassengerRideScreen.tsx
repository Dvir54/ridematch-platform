import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { isApiError, messageFor } from '../../api/errors'
import { collectFieldErrors } from '../../api/fieldErrors'
import { useCreateRequest, useMyRequestOnRide } from '../../api/hooks/requests'
import type { Ride, RideRequest } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { Button, ButtonLink } from '../../components/Button'
import { SelectField } from '../../components/Field'
import { PersonLine } from '../../components/PersonLine'
import { RequestStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { ErrorNotice, InlineLoader, LoadFailure, MessageScreen } from '../../components/states'
import { formatDateTime } from '../../lib/dates'
import { formatMoneyTotal } from '../../lib/money'
import { paths } from '../../routes'
import { RideFacts } from '../rides/RideFacts'
import { useRouteRide } from '../rides/useRouteRide'
import { CancelRequestAction } from './CancelRequestAction'

/** Asking for seats. Everything that can refuse it is a 409 (CONTRACT §4). */
function RequestSeats({ ride }: { ride: Ride }) {
  const [seats, setSeats] = useState(1)
  const createRequest = useCreateRequest(ride.id)
  const error = createRequest.error
  // `seats_requested` is the only field in this body, and the select only offers
  // values the ride can take — so a 422 here means the server knows something the
  // screen does not, and its words matter more than usual.
  const fromServer = collectFieldErrors(error, { seats_requested: 'seats' } as const)

  // A driver's rejection is final for this ride, so stop offering the button.
  const refused = isApiError(error) && error.is('PREVIOUSLY_REJECTED')

  if (ride.status !== 'upcoming') {
    return (
      <p className="text-sm text-ink-70">
        This ride is {ride.status}, so it is not taking requests.
      </p>
    )
  }

  if (refused) {
    return <ErrorNotice>{messageFor(error)}</ErrorNotice>
  }

  const choices = Array.from({ length: Math.min(ride.available_seats, 8) }, (_, i) => i + 1)

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <ErrorNotice>
          {messageFor(error)}
          {fromServer.rest.map((message) => (
            <span key={message} className="mt-1 block font-normal">
              {message}
            </span>
          ))}
        </ErrorNotice>
      ) : null}

      {choices.length > 1 ? (
        <SelectField
          label="How many seats"
          value={seats}
          error={fromServer.fields.seats}
          onChange={(event) => setSeats(Number(event.target.value))}
        >
          {choices.map((count) => (
            <option key={count} value={count}>
              {count === 1 ? '1 seat' : `${count} seats`}
            </option>
          ))}
        </SelectField>
      ) : null}

      <p className="tnum text-sm text-ink-70">
        {formatMoneyTotal(ride.price_per_seat, seats)} in total, paid to the driver in person.
      </p>

      <Button
        disabled={createRequest.isPending}
        onClick={() => createRequest.mutate({ seats_requested: seats })}
      >
        {createRequest.isPending ? 'Asking…' : 'Ask for a seat'}
      </Button>
    </div>
  )
}

/** The state of a request the passenger already made on this ride. */
function MyRequest({ request }: { request: RideRequest }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <p className="tnum text-sm">
          You asked for{' '}
          <span className="font-semibold">
            {request.seats_requested === 1 ? '1 seat' : `${request.seats_requested} seats`}
          </span>{' '}
          on {formatDateTime(request.requested_at)}
        </p>
        <RequestStatusPill status={request.status} />
      </div>

      {request.status === 'pending' ? (
        <p className="text-sm text-ink-70">
          The driver has not answered yet. You will get a notification either way.
        </p>
      ) : null}
      {request.status === 'approved' ? (
        <p className="text-sm text-ink-70">
          Your seat is confirmed. The driver&apos;s plate is on the ride above.
        </p>
      ) : null}
      {request.status === 'rejected' ? (
        <p className="text-sm text-ink-70">
          The driver turned this down, and that is final for this ride.
        </p>
      ) : null}

      <CancelRequestAction request={request} />
    </div>
  )
}

export function PassengerRideScreen() {
  const me = useCurrentUser()
  const { rideId, query } = useRouteRide()
  const mine = useMyRequestOnRide(rideId)

  if (rideId === undefined) {
    return (
      <MessageScreen
        title="No such ride"
        body="That link does not point at a ride."
        action={<ButtonLink to={paths.passengerTrips}>Back to my trips</ButtonLink>}
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
  // Your own ride belongs on the driver's half, where you can act on it.
  if (ride.driver.id === me.id) return <Navigate to={paths.driverRide(ride.id)} replace />

  return (
    <>
      <TabHeader title="This ride" />
      <div className="flex flex-col gap-6">
        <RideFacts ride={ride} />

        <section>
          <h2 className="mb-2 text-lg">The driver</h2>
          <PersonLine person={ride.driver} role="driver" />
        </section>

        <section>
          <h2 className="mb-3 text-lg">Your seat</h2>
          {mine.isPending ? (
            <InlineLoader label="Checking whether you already asked" />
          ) : mine.data ? (
            <MyRequest request={mine.data} />
          ) : (
            <RequestSeats ride={ride} />
          )}
        </section>
      </div>
    </>
  )
}
