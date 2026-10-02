import { useState } from 'react'
import { messageFor } from '../../api/errors'
import { useAdminAnalytics } from '../../api/hooks/admin'
import { StatsGrid } from '../../components/StatsGrid'
import { TextField } from '../../components/Field'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { dateTimeLocalToIso, isoToDateTimeLocal } from '../../lib/dates'

function defaultRange() {
  const to = new Date()
  const from = new Date(to.getTime() - 30 * 24 * 3_600_000)
  return { from: isoToDateTimeLocal(from.toISOString()), to: isoToDateTimeLocal(to.toISOString()) }
}

function percent(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`
}

export function AdminAnalyticsScreen() {
  const [range, setRange] = useState(defaultRange)
  const from = dateTimeLocalToIso(range.from)
  const to = dateTimeLocalToIso(range.to)

  const analytics = useAdminAnalytics(from ?? '', to ?? '')

  return (
    <>
      <div className="mb-5 flex flex-wrap gap-3">
        <div className="min-w-[11rem] flex-1">
          <TextField
            label="From"
            type="datetime-local"
            value={range.from}
            onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))}
          />
        </div>
        <div className="min-w-[11rem] flex-1">
          <TextField
            label="To"
            type="datetime-local"
            value={range.to}
            onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))}
          />
        </div>
      </div>

      {!from || !to ? (
        <EmptyState title="Pick a range" body="Choose a from and to date to see the numbers." />
      ) : null}

      {analytics.isPending && from && to ? <InlineLoader label="Loading analytics" /> : null}

      {analytics.isError ? (
        <LoadFailure
          title="Analytics did not load"
          message={messageFor(analytics.error)}
          onRetry={() => void analytics.refetch()}
        />
      ) : null}

      {analytics.data ? (
        <div className="flex flex-col gap-5">
          <div>
            <h2 className="mb-2 text-sm font-semibold">Rides</h2>
            <StatsGrid
              items={[
                { label: 'Created', value: analytics.data.rides_created },
                { label: 'Completed', value: analytics.data.rides_completed },
                { label: 'Cancelled', value: analytics.data.rides_cancelled },
              ]}
            />
            <p className="tnum mt-2 text-sm text-ink-70">
              Completion rate: {percent(analytics.data.completion_rate)}
            </p>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-semibold">Requests</h2>
            <StatsGrid
              items={[{ label: 'Created', value: analytics.data.requests_created }]}
            />
            <p className="tnum mt-2 text-sm text-ink-70">
              Approval rate: {percent(analytics.data.approval_rate)}
            </p>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-semibold">Users</h2>
            <StatsGrid
              items={[
                { label: 'Active', value: analytics.data.active_users },
                { label: 'New', value: analytics.data.new_users },
              ]}
            />
          </div>
        </div>
      ) : null}
    </>
  )
}
