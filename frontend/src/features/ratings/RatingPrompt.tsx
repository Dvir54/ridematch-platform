import { Link } from 'react-router-dom'
import { usePendingRatings } from '../../api/hooks/ratings'
import { paths } from '../../routes'

/**
 * Completing a ride opens rating for everyone on it (CONTRACT §4). Shown on
 * both Home screens, since a driver and a passenger both owe ratings — one
 * link at a time, to the oldest one still owed.
 */
export function RatingPrompt() {
  const pending = usePendingRatings()
  const rows = pending.data
  if (!rows || rows.length === 0) return null

  const next = rows[0]

  return (
    <Link
      to={paths.rate(next.ride.id, next.to_user.id)}
      className="mb-5 block rounded-card border border-signal-deep/40 bg-signal/15 p-4 transition-colors hover:border-signal-deep"
    >
      <p className="text-sm font-semibold">
        {rows.length === 1 ? 'Rate your ride' : `Rate ${rows.length} rides`}
      </p>
      <p className="mt-0.5 text-sm text-ink-70">
        How was {next.to_user.name} as a {next.role_rated}?
      </p>
    </Link>
  )
}
