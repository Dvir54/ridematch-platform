import { useState } from 'react'
import type { FormEvent } from 'react'
import { useSearchRides } from '../../api/hooks/search'
import type { SearchParams } from '../../api/keys'
import { messageFor } from '../../api/errors'
import type { RideMatch, SearchSort } from '../../api/types'
import { AddressField } from '../../components/AddressField'
import { SelectField, TextField } from '../../components/Field'
import { Button } from '../../components/Button'
import { RideCard } from '../../components/RideCard'
import { MatchBadge, RequestStatusPill } from '../../components/StatusPill'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { dateTimeLocalToIso, soonestDepartureInput } from '../../lib/dates'
import { isValidMoney, MONEY_HINT, toMoney } from '../../lib/money'
import { paths } from '../../routes'
import type { AddressValue } from '../../lib/mapbox'

const SEAT_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8]

const SORTS: { id: SearchSort; label: string }[] = [
  { id: 'best_match', label: 'Best match' },
  { id: 'earliest', label: 'Earliest' },
  { id: 'cheapest', label: 'Cheapest' },
]

interface Values {
  from: AddressValue | null
  to: AddressValue | null
  departure: string
  seats: number
  budget: string
}

type FieldKey = 'from' | 'to' | 'departure' | 'budget'
type Errors = Partial<Record<FieldKey, string>>

function validate(values: Values): Errors {
  const errors: Errors = {}
  if (!values.from) errors.from = 'Choose a pickup point from the suggestions.'
  if (!values.to) errors.to = 'Choose a destination from the suggestions.'
  if (!values.departure) errors.departure = 'Say when you want to leave.'
  if (values.budget.trim() && !isValidMoney(values.budget)) errors.budget = MONEY_HINT
  return errors
}

/** One ride found by `/search`, with the match score and the passenger's own history on it. */
function ResultCard({ match }: { match: RideMatch }) {
  const { ride, match_score: score } = match
  const declined = ride.my_request?.status === 'rejected'

  return (
    <RideCard
      ride={ride}
      to={paths.passengerRide(ride.id)}
      badge={<MatchBadge score={score} />}
      footer={
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-70">
          <span>{ride.driver.name} driving</span>
          {declined ? <RequestStatusPill status="rejected" /> : null}
        </p>
      }
    />
  )
}

export function SearchScreen() {
  const [values, setValues] = useState<Values>({
    from: null,
    to: null,
    departure: soonestDepartureInput(),
    seats: 1,
    budget: '',
  })
  const [errors, setErrors] = useState<Errors>({})
  const [submitted, setSubmitted] = useState<SearchParams | null>(null)

  const results = useSearchRides(submitted)

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function toParams(values: Values, sort: SearchSort): SearchParams | null {
    const departureIso = dateTimeLocalToIso(values.departure)
    if (!values.from || !values.to || !departureIso) return null
    return {
      start_lat: values.from.lat,
      start_lng: values.from.lng,
      end_lat: values.to.lat,
      end_lng: values.to.lng,
      time: departureIso,
      budget: values.budget.trim() ? (toMoney(values.budget) ?? undefined) : undefined,
      seats: values.seats,
      sort,
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const found = validate(values)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setSubmitted(toParams(values, submitted?.sort ?? 'best_match'))
  }

  function changeSort(sort: SearchSort) {
    setSubmitted((current) => (current ? { ...current, sort } : current))
  }

  return (
    <>
      <TabHeader
        title="Search"
        lead="RideMatch scores every driver heading your way and ranks them."
      />

      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        <AddressField
          label="Pickup point"
          placeholder="Where you set off from"
          hint="Start typing, then pick a place so the map knows where it is."
          value={values.from}
          error={errors.from}
          onChange={(value) => set('from', value)}
        />
        <AddressField
          label="Destination"
          placeholder="Where you are heading"
          value={values.to}
          error={errors.to}
          onChange={(value) => set('to', value)}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Departure"
            type="datetime-local"
            min={soonestDepartureInput()}
            value={values.departure}
            error={errors.departure}
            onChange={(event) => set('departure', event.target.value)}
          />
          <SelectField
            label="Seats"
            value={values.seats}
            onChange={(event) => set('seats', Number(event.target.value))}
          >
            {SEAT_CHOICES.map((count) => (
              <option key={count} value={count}>
                {count === 1 ? '1 seat' : `${count} seats`}
              </option>
            ))}
          </SelectField>
        </div>
        <TextField
          label="Budget"
          optional
          inputMode="decimal"
          placeholder="25.00"
          hint="The most you want to pay per seat."
          value={values.budget}
          error={errors.budget}
          onChange={(event) => set('budget', event.target.value)}
        />

        <Button type="submit" full disabled={results.isFetching}>
          {results.isFetching ? 'Searching…' : 'Search'}
        </Button>
      </form>

      {submitted ? (
        <div className="mt-8">
          <div role="group" aria-label="Sort results" className="mb-5 flex gap-2">
            {SORTS.map((sort) => (
              <button
                key={sort.id}
                type="button"
                aria-pressed={sort.id === submitted.sort}
                onClick={() => changeSort(sort.id)}
                className={`rounded-full border px-3 py-1 text-sm font-semibold ${
                  sort.id === submitted.sort
                    ? 'border-ink bg-ink text-surface'
                    : 'border-hairline text-ink-70 hover:border-ink hover:text-ink'
                }`}
              >
                {sort.label}
              </button>
            ))}
          </div>

          {results.isPending ? <InlineLoader label="Scoring rides for you" /> : null}

          {results.isError ? (
            <LoadFailure
              title="Search did not load"
              message={messageFor(results.error)}
              onRetry={() => void results.refetch()}
            />
          ) : null}

          {results.data?.length === 0 ? (
            <EmptyState
              title="Nothing matches yet"
              body="Try a wider time window, a higher budget, or fewer seats."
            />
          ) : null}

          <div className="flex flex-col gap-4">
            {results.data?.map((match) => (
              <ResultCard key={match.ride.id} match={match} />
            ))}
          </div>
        </div>
      ) : null}
    </>
  )
}
