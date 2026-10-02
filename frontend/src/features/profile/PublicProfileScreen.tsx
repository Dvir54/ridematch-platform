import { useParams } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useUserRatings } from '../../api/hooks/ratings'
import { useUserPublic } from '../../api/hooks/users'
import type { Rating } from '../../api/types'
import { ButtonLink } from '../../components/Button'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure, MessageScreen } from '../../components/states'
import { formatDay } from '../../lib/dates'
import { formatRating } from '../../lib/rating'
import { paths } from '../../routes'

function RatingRow({ rating }: { rating: Rating }) {
  return (
    <li className="rounded-card border border-hairline bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold">{rating.from_user.name}</p>
        <p className="tnum text-sm">{rating.score}/5</p>
      </div>
      {rating.comment ? <p className="mt-1 text-sm text-ink-70">{rating.comment}</p> : null}
      {rating.tags.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {rating.tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full border border-hairline px-2 py-0.5 text-xs text-ink-70"
            >
              {tag.replace(/_/g, ' ')}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="tnum mt-2 text-xs text-ink-45">{formatDay(rating.created_at)}</p>
    </li>
  )
}

export function PublicProfileScreen() {
  const { userId: param } = useParams<{ userId: string }>()
  const userId = Number(param)
  const valid = Number.isInteger(userId) && userId > 0

  const user = useUserPublic(valid ? userId : undefined)
  const ratings = useUserRatings(valid ? userId : undefined)

  if (!valid) {
    return (
      <MessageScreen
        title="No such profile"
        body="That link does not point at a RideMatch user."
        action={<ButtonLink to={paths.app}>Back home</ButtonLink>}
      />
    )
  }

  if (user.isPending) return <InlineLoader label="Loading this profile" />
  if (user.isError) {
    return (
      <LoadFailure
        title="This profile did not load"
        message={messageFor(user.error)}
        onRetry={() => void user.refetch()}
      />
    )
  }

  const person = user.data
  const memberSince = new Date(person.created_at).toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  })

  return (
    <>
      <TabHeader title={person.name} lead={`Member since ${memberSince}`} />

      <section className="rounded-card border border-hairline bg-surface px-5 py-2">
        <h2 className="sr-only">Ratings</h2>
        <dl>
          <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3">
            <dt className="text-sm text-ink-70">As a driver</dt>
            <dd className="tnum text-right font-medium">
              {formatRating(person.driver_rating, person.driver_rating_count)}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 py-3">
            <dt className="text-sm text-ink-70">As a passenger</dt>
            <dd className="tnum text-right font-medium">
              {formatRating(person.passenger_rating, person.passenger_rating_count)}
            </dd>
          </div>
        </dl>
      </section>

      {person.vehicle ? (
        <section className="mt-5 rounded-card border border-hairline bg-surface px-5 py-4">
          <h2 className="text-sm font-semibold">Car</h2>
          <p className="mt-2 text-sm">
            {person.vehicle.color} {person.vehicle.make} {person.vehicle.model}
          </p>
        </section>
      ) : null}

      <section className="mt-6">
        <h2 className="mb-3 text-lg">What people said</h2>

        {ratings.isPending ? <InlineLoader label="Loading ratings" /> : null}
        {ratings.isError ? (
          <LoadFailure
            title="Ratings did not load"
            message={messageFor(ratings.error)}
            onRetry={() => void ratings.refetch()}
          />
        ) : null}
        {ratings.data && ratings.data.length === 0 ? (
          <EmptyState title="No ratings yet" body="Nothing has been said about this person yet." />
        ) : null}

        {ratings.data && ratings.data.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {ratings.data.map((rating) => (
              <RatingRow key={rating.id} rating={rating} />
            ))}
          </ul>
        ) : null}
      </section>
    </>
  )
}
