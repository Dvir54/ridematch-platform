import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Ride } from '../api/types'
import { formatDateTime } from '../lib/dates'
import { shortAddress } from '../lib/address'
import { formatMoney } from '../lib/money'
import { seatsLine } from '../lib/seats'
import { RouteRail } from './RouteRail'

export interface RideCardProps {
  ride: Ride
  /** Where tapping the card goes. Omit for a card that is not a link. */
  to?: string
  /** Top-right slot — normally a status pill. */
  badge?: ReactNode
  /** An extra line under the seats, e.g. who asked or what was confirmed. */
  footer?: ReactNode
}

const shell = 'block rounded-card border border-hairline bg-surface p-4 text-left'

/**
 * One ride, drawn the same way everywhere it appears — the driver's board, the
 * passenger's trips, a request. The rail is the app's signature, so a ride is
 * recognisable before a single word is read.
 */
export function RideCard({ ride, to, badge, footer }: RideCardProps) {
  const body = (
    <>
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="tnum text-sm font-semibold">{formatDateTime(ride.departure_time)}</p>
        {badge}
      </div>

      <RouteRail from={shortAddress(ride.start_address)} to={shortAddress(ride.end_address)} />

      <p className="tnum mt-3 text-sm text-ink-70">
        {seatsLine(ride)} · {formatMoney(ride.price_per_seat)} a seat
      </p>
      {footer}
    </>
  )

  if (!to) return <article className={shell}>{body}</article>

  return (
    <Link to={to} className={`${shell} transition-colors hover:border-ink`}>
      {body}
    </Link>
  )
}
