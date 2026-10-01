import type { Ride } from '../../api/types'
import { RouteRail } from '../../components/RouteRail'
import { RideStatusPill } from '../../components/StatusPill'
import { formatDateTime } from '../../lib/dates'
import { formatMoney } from '../../lib/money'
import { seatsLine } from '../../lib/seats'

function preferenceChips(ride: Ride): string[] {
  const chips = [
    ride.preferences.smoking ? 'Smoking allowed' : 'No smoking',
    ride.preferences.pets ? 'Pets welcome' : 'No pets',
    ride.preferences.music ? 'Music on' : 'Quiet ride',
  ]
  if (ride.preferences.gender_only) chips.push("Same gender as the driver only")
  return chips
}

/**
 * Everything true about one ride, laid out the same way for the driver and for a
 * passenger. The two screens differ in what you can *do*, never in what the ride
 * is — so the facts live here once.
 */
export function RideFacts({ ride }: { ride: Ride }) {
  const vehicle = ride.driver.vehicle

  return (
    <section className="rounded-card border border-hairline bg-surface p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <p className="tnum text-lg font-semibold">{formatDateTime(ride.departure_time)}</p>
        <RideStatusPill status={ride.status} />
      </div>

      <RouteRail size="display" from={ride.start_address} to={ride.end_address} />

      <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-hairline pt-4 text-sm">
        <div>
          <dt className="text-ink-45">Seats</dt>
          <dd className="tnum mt-0.5 font-semibold">{seatsLine(ride)}</dd>
        </div>
        <div>
          <dt className="text-ink-45">Price a seat</dt>
          <dd className="tnum mt-0.5 font-semibold">{formatMoney(ride.price_per_seat)}</dd>
        </div>
      </dl>

      <ul className="mt-4 flex flex-wrap gap-2">
        {preferenceChips(ride).map((chip) => (
          <li
            key={chip}
            className="rounded-full border border-hairline px-2.5 py-0.5 text-xs font-medium text-ink-70"
          >
            {chip}
          </li>
        ))}
      </ul>

      {vehicle ? (
        <div className="mt-4 border-t border-hairline pt-4 text-sm">
          <p className="text-ink-45">The car</p>
          <p className="mt-0.5 font-semibold">
            {vehicle.color} {vehicle.make} {vehicle.model}
          </p>
          {/* The plate reaches the driver and approved passengers only (D14). */}
          {ride.driver_vehicle_plate ? (
            <p className="tnum mt-0.5 text-ink-70">Plate {ride.driver_vehicle_plate}</p>
          ) : null}
        </div>
      ) : null}

      {ride.notes ? (
        <div className="mt-4 border-t border-hairline pt-4 text-sm">
          <p className="text-ink-45">From the driver</p>
          <p className="mt-0.5 whitespace-pre-line">{ride.notes}</p>
        </div>
      ) : null}
    </section>
  )
}
