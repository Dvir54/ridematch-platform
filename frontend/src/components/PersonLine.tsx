import { Link } from 'react-router-dom'
import type { UserPublic } from '../api/types'
import { paths } from '../routes'

/**
 * Who you are riding with. The rating shown is the one for the role they play on
 * this ride — a good driver and a good passenger are different claims, and the
 * contract keeps two averages for exactly that reason.
 */
export function PersonLine({
  person,
  role,
  prefix,
}: {
  person: UserPublic
  role: 'driver' | 'passenger'
  /** "Driven by", "Asked by" — says why this person is on screen. */
  prefix?: string
}) {
  const rating = role === 'driver' ? person.driver_rating : person.passenger_rating
  const count = role === 'driver' ? person.driver_rating_count : person.passenger_rating_count

  return (
    <p className="text-sm">
      {prefix ? <span className="text-ink-45">{prefix} </span> : null}
      {person.id > 0 ? (
        <Link to={paths.user(person.id)} className="font-semibold underline decoration-ink/30 underline-offset-4">
          {person.name}
        </Link>
      ) : (
        <span className="font-semibold">{person.name}</span>
      )}
      {rating !== null && rating !== undefined ? (
        <span className="tnum text-ink-70">
          {' · '}
          {rating.toFixed(1)}★ from {count} {count === 1 ? 'rating' : 'ratings'}
        </span>
      ) : (
        <span className="text-ink-45">{' · '}no ratings yet</span>
      )}
    </p>
  )
}
