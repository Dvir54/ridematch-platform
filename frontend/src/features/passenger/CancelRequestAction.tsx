import { messageFor } from '../../api/errors'
import { useCancelRequest } from '../../api/hooks/requests'
import type { RequestStatus, Ride } from '../../api/types'
import { ConfirmAction } from '../../components/ConfirmAction'
import { ErrorNotice } from '../../components/states'
import { canCancelApprovedYet, formatDateTime } from '../../lib/dates'

export interface CancelRequestActionProps {
  ride: Ride
  requestId: number
  status: RequestStatus
}

/**
 * Giving a seat back. A pending request can go any time; an approved one locks
 * an hour before departure (D15), so the lock is explained rather than enforced
 * by a button that answers TOO_LATE_TO_CANCEL.
 *
 * Takes the ride and request fields apart rather than a `RideRequest`, because
 * `Ride.my_request` (the Ride Details screen's source) carries only
 * `{id, status, seats_requested}` — not the full request with its nested ride.
 */
export function CancelRequestAction({ ride, requestId, status }: CancelRequestActionProps) {
  const cancel = useCancelRequest()

  if (status !== 'pending' && status !== 'approved') return null

  const rideOpen = ride.status === 'upcoming' || ride.status === 'full'
  if (!rideOpen) {
    return (
      <p className="text-sm text-ink-70">
        This ride is {ride.status}, so the seat can no longer be given back.
      </p>
    )
  }

  if (status === 'approved' && !canCancelApprovedYet(ride.departure_time)) {
    return (
      <p className="text-sm text-ink-70">
        Confirmed seats lock an hour before departure, so this one is yours now. Tell the driver
        directly if your plans changed.
      </p>
    )
  }

  const question =
    status === 'approved'
      ? `The driver gets the seat back and is told you are not coming. You can cancel until an hour before ${formatDateTime(ride.departure_time)}.`
      : 'The driver stops seeing your request. You can ask again later if seats are still free.'

  return (
    <div className="flex flex-col gap-3">
      {cancel.error ? <ErrorNotice>{messageFor(cancel.error)}</ErrorNotice> : null}
      <ConfirmAction
        label={status === 'approved' ? 'Give up the seat' : 'Withdraw the request'}
        question={question}
        confirmLabel={status === 'approved' ? 'Give up the seat' : 'Withdraw it'}
        pending={cancel.isPending}
        onConfirm={() => cancel.mutate(requestId)}
      />
    </div>
  )
}
