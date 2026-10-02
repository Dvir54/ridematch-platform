import { Link, useParams } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useAdminUserDetail, useDeactivateUser, useReactivateUser } from '../../api/hooks/admin'
import type { Rating } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { Button, ButtonLink } from '../../components/Button'
import { ConfirmAction } from '../../components/ConfirmAction'
import { RideCard } from '../../components/RideCard'
import { RequestStatusPill, RideStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, ErrorNotice, InlineLoader, LoadFailure, MessageScreen } from '../../components/states'
import { formatDay } from '../../lib/dates'
import { formatRating } from '../../lib/rating'
import { paths } from '../../routes'

function RatingRow({ rating }: { rating: Rating }) {
  return (
    <li className="rounded-card border border-hairline bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold">
          {rating.from_user.name} <span className="font-normal text-ink-45">rated as {rating.role_rated}</span>
        </p>
        <p className="tnum text-sm">{rating.score}/5</p>
      </div>
      {rating.comment ? <p className="mt-1 text-sm text-ink-70">{rating.comment}</p> : null}
      <p className="tnum mt-2 text-xs text-ink-45">{formatDay(rating.created_at)}</p>
    </li>
  )
}

export function AdminUserDetailScreen() {
  const { userId: param } = useParams<{ userId: string }>()
  const userId = Number(param)
  const valid = Number.isInteger(userId) && userId > 0

  const me = useCurrentUser()
  const detail = useAdminUserDetail(valid ? userId : undefined)
  const deactivate = useDeactivateUser()
  const reactivate = useReactivateUser()

  if (!valid) {
    return (
      <MessageScreen
        title="No such user"
        body="That link does not point at a RideMatch user."
        action={<ButtonLink to={paths.adminUsers}>Back to users</ButtonLink>}
      />
    )
  }

  if (detail.isPending) return <InlineLoader label="Loading this user" />
  if (detail.isError) {
    return (
      <LoadFailure
        title="This user did not load"
        message={messageFor(detail.error)}
        onRetry={() => void detail.refetch()}
      />
    )
  }

  const { user, rides_as_driver, requests_as_passenger, ratings_received } = detail.data
  const isSelf = user.id === me.id
  const pendingAction = deactivate.isPending || reactivate.isPending

  return (
    <>
      <Link to={paths.adminUsers} className="text-sm text-ink-70 underline decoration-ink/30 underline-offset-4">
        ← All users
      </Link>

      <TabHeader title={user.name} lead={user.email} />

      <section className="rounded-card border border-hairline bg-surface px-5 py-2">
        <dl>
          <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3">
            <dt className="text-sm text-ink-70">Status</dt>
            <dd className="text-right font-medium">{user.is_active ? 'Active' : 'Deactivated'}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3">
            <dt className="text-sm text-ink-70">Role</dt>
            <dd className="text-right font-medium">{user.is_admin ? 'Admin' : 'Member'}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3">
            <dt className="text-sm text-ink-70">Phone</dt>
            <dd className="text-right font-medium">{user.phone ?? 'Not added'}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3">
            <dt className="text-sm text-ink-70">As a driver</dt>
            <dd className="tnum text-right font-medium">
              {formatRating(user.driver_rating, user.driver_rating_count)}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 py-3">
            <dt className="text-sm text-ink-70">As a passenger</dt>
            <dd className="tnum text-right font-medium">
              {formatRating(user.passenger_rating, user.passenger_rating_count)}
            </dd>
          </div>
        </dl>
      </section>

      <div className="mt-5">
        {isSelf ? (
          <p className="text-sm text-ink-45">You can't deactivate your own account.</p>
        ) : deactivate.isError ? (
          <ErrorNotice>{messageFor(deactivate.error)}</ErrorNotice>
        ) : reactivate.isError ? (
          <ErrorNotice>{messageFor(reactivate.error)}</ErrorNotice>
        ) : null}

        {!isSelf && user.is_active ? (
          <ConfirmAction
            label="Deactivate"
            question={`${user.name} will be signed out everywhere and locked out of RideMatch.`}
            confirmLabel="Deactivate"
            pending={deactivate.isPending}
            disabled={pendingAction}
            onConfirm={() => deactivate.mutate(user.id)}
          />
        ) : null}

        {!isSelf && !user.is_active ? (
          <Button
            variant="secondary"
            disabled={pendingAction}
            onClick={() => reactivate.mutate(user.id)}
          >
            {reactivate.isPending ? 'Working…' : 'Reactivate'}
          </Button>
        ) : null}
      </div>

      <section className="mt-6">
        <h2 className="mb-3 text-lg">Rides driven</h2>
        {rides_as_driver.length === 0 ? (
          <EmptyState title="No rides" body="This user has never offered a ride." />
        ) : (
          <div className="flex flex-col gap-3">
            {rides_as_driver.map((ride) => (
              <RideCard key={ride.id} ride={ride} badge={<RideStatusPill status={ride.status} />} />
            ))}
          </div>
        )}
      </section>

      <section className="mt-6">
        <h2 className="mb-3 text-lg">Requests made</h2>
        {requests_as_passenger.length === 0 ? (
          <EmptyState title="No requests" body="This user has never asked for a seat." />
        ) : (
          <ul className="flex flex-col gap-3">
            {requests_as_passenger.map((req) => (
              <li key={req.id} className="rounded-card border border-hairline bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm">
                    {req.seats_requested === 1 ? '1 seat' : `${req.seats_requested} seats`} on{' '}
                    {req.ride.start_address} → {req.ride.end_address}
                  </p>
                  <RequestStatusPill status={req.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h2 className="mb-3 text-lg">Ratings received</h2>
        {ratings_received.length === 0 ? (
          <EmptyState title="No ratings" body="Nobody has rated this person yet." />
        ) : (
          <ul className="flex flex-col gap-3">
            {ratings_received.map((rating) => (
              <RatingRow key={rating.id} rating={rating} />
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
