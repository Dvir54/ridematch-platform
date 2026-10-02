import { useState } from 'react'
import { messageFor } from '../../api/errors'
import { useAdminRides, useForceCancelRide } from '../../api/hooks/admin'
import type { Ride, RideStatus } from '../../api/types'
import { Button } from '../../components/Button'
import { TextField, TextareaField } from '../../components/Field'
import { RideCard } from '../../components/RideCard'
import { RideStatusPill } from '../../components/StatusPill'
import { EmptyState, ErrorNotice, InlineLoader, LoadFailure } from '../../components/states'
import { dateTimeLocalToIso } from '../../lib/dates'
import { LIMIT, Pager } from './Pager'

const STATUSES: RideStatus[] = ['upcoming', 'full', 'in_progress', 'completed', 'cancelled']
const TERMINAL: RideStatus[] = ['completed', 'cancelled']

function ForceCancelAction({ ride }: { ride: Ride }) {
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const forceCancel = useForceCancelRide()

  if (TERMINAL.includes(ride.status)) return null

  if (!asking) {
    return (
      <Button variant="secondary" onClick={() => setAsking(true)}>
        Force-cancel
      </Button>
    )
  }

  return (
    <div className="mt-3 rounded-card border border-alert/30 bg-alert-wash p-4">
      <TextareaField
        label="Reason"
        hint="Goes to the driver as the cancellation notice."
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        maxLength={500}
        rows={2}
      />
      {forceCancel.isError ? (
        <div className="mt-2">
          <ErrorNotice>{messageFor(forceCancel.error)}</ErrorNotice>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          disabled={!reason.trim() || forceCancel.isPending}
          onClick={() =>
            forceCancel.mutate(
              { rideId: ride.id, reason: reason.trim() },
              { onSuccess: () => setAsking(false) },
            )
          }
        >
          {forceCancel.isPending ? 'Working…' : 'Confirm cancel'}
        </Button>
        <Button variant="quiet" disabled={forceCancel.isPending} onClick={() => setAsking(false)}>
          Keep it
        </Button>
      </div>
    </div>
  )
}

export function AdminRidesScreen() {
  const [statuses, setStatuses] = useState<RideStatus[]>([])
  const [driverIdInput, setDriverIdInput] = useState('')
  const [fromLocal, setFromLocal] = useState('')
  const [toLocal, setToLocal] = useState('')
  const [offset, setOffset] = useState(0)

  const driverId = Number(driverIdInput)
  const rides = useAdminRides({
    status: statuses.length ? statuses : undefined,
    driver_id: driverIdInput.trim() && Number.isInteger(driverId) && driverId > 0 ? driverId : undefined,
    from: fromLocal ? (dateTimeLocalToIso(fromLocal) ?? undefined) : undefined,
    to: toLocal ? (dateTimeLocalToIso(toLocal) ?? undefined) : undefined,
    limit: LIMIT,
    offset,
  })

  function toggleStatus(status: RideStatus) {
    setStatuses((current) =>
      current.includes(status) ? current.filter((s) => s !== status) : [...current, status],
    )
    setOffset(0)
  }

  return (
    <>
      <div className="mb-5 flex flex-col gap-4">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
          {STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              aria-pressed={statuses.includes(status)}
              onClick={() => toggleStatus(status)}
              className={`rounded-full border px-3 py-1 text-sm font-semibold capitalize ${
                statuses.includes(status)
                  ? 'border-ink bg-ink text-surface'
                  : 'border-hairline text-ink-70 hover:border-ink hover:text-ink'
              }`}
            >
              {status.replace('_', ' ')}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="w-32">
            <TextField
              label="Driver ID"
              inputMode="numeric"
              value={driverIdInput}
              onChange={(event) => {
                setDriverIdInput(event.target.value)
                setOffset(0)
              }}
            />
          </div>
          <div className="min-w-[11rem] flex-1">
            <TextField
              label="Departs from"
              type="datetime-local"
              value={fromLocal}
              onChange={(event) => {
                setFromLocal(event.target.value)
                setOffset(0)
              }}
            />
          </div>
          <div className="min-w-[11rem] flex-1">
            <TextField
              label="Departs before"
              type="datetime-local"
              value={toLocal}
              onChange={(event) => {
                setToLocal(event.target.value)
                setOffset(0)
              }}
            />
          </div>
        </div>
      </div>

      {rides.isPending ? <InlineLoader label="Loading rides" /> : null}

      {rides.isError ? (
        <LoadFailure
          title="Rides did not load"
          message={messageFor(rides.error)}
          onRetry={() => void rides.refetch()}
        />
      ) : null}

      {rides.data?.data.length === 0 ? (
        <EmptyState title="No rides match" body="Try different filters." />
      ) : null}

      <div className="flex flex-col gap-3">
        {rides.data?.data.map((ride) => (
          <RideCard
            key={ride.id}
            ride={ride}
            badge={<RideStatusPill status={ride.status} />}
            footer={
              <div className="mt-3">
                <p className="text-sm text-ink-70">Driven by {ride.driver.name}</p>
                <div className="mt-2">
                  <ForceCancelAction ride={ride} />
                </div>
              </div>
            }
          />
        ))}
      </div>

      {rides.data ? <Pager offset={offset} total={rides.data.total} onChange={setOffset} /> : null}
    </>
  )
}
