import type { RequestStatus, RideStatus } from '../api/types'

/**
 * A status is read at a glance, so each one gets a word a person would actually
 * say rather than the contract's enum. The colour is a second channel, never the
 * only one.
 */
const RIDE: Record<RideStatus, { label: string; tone: string }> = {
  upcoming: { label: 'Upcoming', tone: 'border-ink/25 text-ink' },
  full: { label: 'Full', tone: 'border-signal-deep/40 bg-signal/15 text-signal-deep' },
  in_progress: { label: 'On the road', tone: 'border-go/40 bg-go/10 text-go' },
  completed: { label: 'Completed', tone: 'border-hairline text-ink-45' },
  cancelled: { label: 'Cancelled', tone: 'border-alert/30 bg-alert-wash text-alert' },
}

const REQUEST: Record<RequestStatus, { label: string; tone: string }> = {
  pending: { label: 'Waiting on the driver', tone: 'border-signal-deep/40 bg-signal/15 text-signal-deep' },
  approved: { label: 'Seat confirmed', tone: 'border-go/40 bg-go/10 text-go' },
  rejected: { label: 'Declined', tone: 'border-alert/30 bg-alert-wash text-alert' },
  cancelled: { label: 'Cancelled', tone: 'border-hairline text-ink-45' },
}

const base =
  'inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold'

export function RideStatusPill({ status }: { status: RideStatus }) {
  const { label, tone } = RIDE[status]
  return <span className={`${base} ${tone}`}>{label}</span>
}

export function RequestStatusPill({ status }: { status: RequestStatus }) {
  const { label, tone } = REQUEST[status]
  return <span className={`${base} ${tone}`}>{label}</span>
}

/** A search result's `match_score` (CONTRACT §7), kept ≥ 40 by the server. */
export function MatchBadge({ score }: { score: number }) {
  const tone =
    score >= 70
      ? 'border-go/40 bg-go/10 text-go'
      : score >= 55
        ? 'border-signal-deep/40 bg-signal/15 text-signal-deep'
        : 'border-ink/25 text-ink'
  return <span className={`${base} tnum ${tone}`}>{Math.round(score)}% match</span>
}
