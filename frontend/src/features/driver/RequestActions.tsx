import { useApproveRequest, useRejectRequest } from '../../api/hooks/requests'
import { messageFor } from '../../api/errors'
import type { RideRequest } from '../../api/types'
import { Button } from '../../components/Button'
import { ConfirmAction } from '../../components/ConfirmAction'
import { ErrorNotice } from '../../components/states'

/**
 * Approve and decline for one request. Each row owns its own mutations, so a
 * failure — most often NOT_ENOUGH_SEATS, when the last seat went to someone else
 * between loading the list and pressing the button — lands next to the person it
 * concerns instead of at the top of the screen.
 */
export function RequestActions({ request }: { request: RideRequest }) {
  const approve = useApproveRequest()
  const reject = useRejectRequest()
  const busy = approve.isPending || reject.isPending
  const failure = approve.error ?? reject.error

  if (request.status !== 'pending') return null

  return (
    <div className="mt-3 flex flex-col gap-3">
      {failure ? <ErrorNotice>{messageFor(failure)}</ErrorNotice> : null}
      <div className="flex flex-wrap items-start gap-2">
        <Button disabled={busy} onClick={() => approve.mutate(request.id)}>
          {approve.isPending ? 'Approving…' : 'Approve'}
        </Button>
        <ConfirmAction
          label="Decline"
          question="Declining is final for this ride — they cannot ask again."
          confirmLabel="Decline the seat"
          pending={reject.isPending}
          disabled={busy}
          onConfirm={() => reject.mutate(request.id)}
        />
      </div>
    </div>
  )
}
