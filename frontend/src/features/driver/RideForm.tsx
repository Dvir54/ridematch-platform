import { useState } from 'react'
import type { FormEvent } from 'react'
import { messageFor } from '../../api/errors'
import type { Ride, RideCreate, RidePreferences, RideUpdate } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { AddressField } from '../../components/AddressField'
import { Button } from '../../components/Button'
import { SelectField, SwitchField, TextareaField, TextField } from '../../components/Field'
import { ErrorNotice } from '../../components/states'
import {
  dateTimeLocalToIso,
  formatDateTime,
  isoToDateTimeLocal,
  soonestDepartureInput,
} from '../../lib/dates'
import type { AddressValue } from '../../lib/mapbox'
import { MONEY_HINT, isValidMoney, toMoney } from '../../lib/money'
import { shortAddress } from '../../lib/address'

const SEAT_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8]

interface Values {
  start: AddressValue | null
  end: AddressValue | null
  departure: string
  capacity: number
  price: string
  notes: string
  preferences: RidePreferences
}

type Errors = Partial<Record<'start' | 'end' | 'departure' | 'capacity' | 'price', string>>

function initialValues(ride: Ride | undefined): Values {
  if (!ride) {
    return {
      start: null,
      end: null,
      departure: '',
      capacity: 3,
      price: '',
      notes: '',
      preferences: { smoking: false, pets: false, music: true, gender_only: false },
    }
  }
  return {
    start: { address: ride.start_address, lat: ride.start_lat, lng: ride.start_lng },
    end: { address: ride.end_address, lat: ride.end_lat, lng: ride.end_lng },
    departure: isoToDateTimeLocal(ride.departure_time),
    capacity: ride.capacity,
    price: Number(ride.price_per_seat).toFixed(2),
    notes: ride.notes ?? '',
    // Reads always carry all four keys, so this is the ride's real setting.
    preferences: { ...ride.preferences },
  }
}

/** Only what changed, because PATCH shallow-merges (D16) and locks some fields. */
function changedFields(ride: Ride, values: Values, departureIso: string): RideUpdate {
  const patch: RideUpdate = {}

  if (values.start && values.start.address !== ride.start_address) {
    patch.start_address = values.start.address
    patch.start_lat = values.start.lat
    patch.start_lng = values.start.lng
  }
  if (values.end && values.end.address !== ride.end_address) {
    patch.end_address = values.end.address
    patch.end_lat = values.end.lat
    patch.end_lng = values.end.lng
  }
  if (departureIso !== ride.departure_time) patch.departure_time = departureIso
  if (values.capacity !== ride.capacity) patch.capacity = values.capacity

  const price = toMoney(values.price)
  if (price && price !== Number(ride.price_per_seat).toFixed(2)) patch.price_per_seat = price

  const notes = values.notes.trim() === '' ? null : values.notes.trim()
  if (notes !== (ride.notes ?? null)) patch.notes = notes

  const preferences = Object.fromEntries(
    (Object.keys(values.preferences) as (keyof RidePreferences)[])
      .filter((key) => values.preferences[key] !== ride.preferences[key])
      .map((key) => [key, values.preferences[key]]),
  )
  if (Object.keys(preferences).length > 0) patch.preferences = preferences

  return patch
}

export interface RideFormProps {
  /** The ride being edited; omitted when offering a new one. */
  ride?: Ride
  submitLabel: string
  pending: boolean
  /** Whatever the mutation threw, shown by `code` (CONTRACT §5). */
  error: unknown
  onCreate?: (body: RideCreate) => void
  onUpdate?: (body: RideUpdate) => void
  onCancel?: () => void
}

/**
 * One form for offering and editing a ride. Editing is the harder half: once a
 * passenger is approved, the route and the departure time are frozen
 * (RIDE_HAS_APPROVED_PASSENGERS), so the form shows them as settled facts rather
 * than offering fields that are guaranteed to fail.
 */
export function RideForm({
  ride,
  submitLabel,
  pending,
  error,
  onCreate,
  onUpdate,
  onCancel,
}: RideFormProps) {
  const me = useCurrentUser()
  const [values, setValues] = useState<Values>(() => initialValues(ride))
  const [errors, setErrors] = useState<Errors>({})

  // available_seats = capacity − approved seats, so the ride itself says how
  // many are already committed. No second request needed.
  const approvedSeats = ride ? ride.capacity - ride.available_seats : 0
  const routeLocked = approvedSeats > 0

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function setPreference(key: keyof RidePreferences, value: boolean) {
    setValues((current) => ({ ...current, preferences: { ...current.preferences, [key]: value } }))
  }

  function validate(departureIso: string | null): Errors {
    const found: Errors = {}
    if (!routeLocked) {
      if (!values.start) found.start = 'Choose a pickup point from the suggestions.'
      if (!values.end) found.end = 'Choose a destination from the suggestions.'
      if (!departureIso) found.departure = 'Say when you are leaving.'
      else if (new Date(departureIso).getTime() <= Date.now()) {
        found.departure = 'Pick a departure time in the future.'
      }
    }
    if (!isValidMoney(values.price)) found.price = MONEY_HINT
    if (ride && values.capacity < approvedSeats) {
      found.capacity = `You have already approved ${approvedSeats} seats.`
    }
    return found
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const departureIso = routeLocked
      ? (ride?.departure_time ?? null)
      : dateTimeLocalToIso(values.departure)

    const found = validate(departureIso)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    const price = toMoney(values.price)
    if (!price || !departureIso) return

    if (ride && onUpdate) {
      onUpdate(changedFields(ride, values, departureIso))
      return
    }
    if (!values.start || !values.end || !onCreate) return

    onCreate({
      start_address: values.start.address,
      start_lat: values.start.lat,
      start_lng: values.start.lng,
      end_address: values.end.address,
      end_lat: values.end.lat,
      end_lng: values.end.lng,
      departure_time: departureIso,
      capacity: values.capacity,
      price_per_seat: price,
      notes: values.notes.trim() === '' ? null : values.notes.trim(),
      preferences: values.preferences,
    })
  }

  const genderOnlyWithoutGender = values.preferences.gender_only && !me.gender

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      {error ? <ErrorNotice>{messageFor(error)}</ErrorNotice> : null}

      {routeLocked && ride ? (
        <section className="rounded-card border border-hairline bg-surface p-4">
          <h2 className="text-sm font-semibold">Route and time are set</h2>
          <p className="mt-1 text-sm text-ink-70">
            {approvedSeats === 1 ? 'One passenger is' : `${approvedSeats} passengers are`} already
            counting on this plan, so it can no longer move. Cancel the ride if it has to change.
          </p>
          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="text-ink-45">From</dt>
              <dd className="font-medium">{shortAddress(ride.start_address)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-ink-45">To</dt>
              <dd className="font-medium">{shortAddress(ride.end_address)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-ink-45">Leaves</dt>
              <dd className="tnum font-medium">{formatDateTime(ride.departure_time)}</dd>
            </div>
          </dl>
        </section>
      ) : (
        <section className="flex flex-col gap-5">
          <AddressField
            label="Pickup point"
            placeholder="Where you set off from"
            hint="Start typing, then pick a place so the map knows where it is."
            value={values.start}
            error={errors.start}
            onChange={(value) => set('start', value)}
          />
          <AddressField
            label="Destination"
            placeholder="Where you are heading"
            value={values.end}
            error={errors.end}
            onChange={(value) => set('end', value)}
          />
          <TextField
            label="Departure"
            type="datetime-local"
            min={soonestDepartureInput()}
            value={values.departure}
            error={errors.departure}
            onChange={(event) => set('departure', event.target.value)}
          />
        </section>
      )}

      <section className="flex flex-col gap-5">
        <SelectField
          label="Seats for passengers"
          hint={
            approvedSeats > 0
              ? `${approvedSeats} already approved, so this cannot go below that.`
              : undefined
          }
          value={values.capacity}
          error={errors.capacity}
          onChange={(event) => set('capacity', Number(event.target.value))}
        >
          {SEAT_CHOICES.map((seats) => (
            <option key={seats} value={seats}>
              {seats === 1 ? '1 seat' : `${seats} seats`}
            </option>
          ))}
        </SelectField>

        <TextField
          label="Price per seat"
          inputMode="decimal"
          placeholder="25.00"
          hint="What each passenger pays you. Paid in person, not through RideMatch."
          value={values.price}
          error={errors.price}
          onChange={(event) => set('price', event.target.value)}
        />

        <TextareaField
          label="Notes"
          optional
          rows={3}
          maxLength={1000}
          placeholder="Where exactly to wait, luggage space, anything else worth saying."
          value={values.notes}
          onChange={(event) => set('notes', event.target.value)}
        />
      </section>

      <section>
        <h2 className="text-sm font-semibold">What the ride is like</h2>
        <p className="mt-1 text-sm text-ink-70">
          Passengers see these before they ask for a seat.
        </p>
        <div className="mt-2 divide-y divide-hairline">
          <SwitchField
            label="Smoking allowed"
            checked={values.preferences.smoking}
            onChange={(checked) => setPreference('smoking', checked)}
          />
          <SwitchField
            label="Pets allowed"
            checked={values.preferences.pets}
            onChange={(checked) => setPreference('pets', checked)}
          />
          <SwitchField
            label="Music on"
            checked={values.preferences.music}
            onChange={(checked) => setPreference('music', checked)}
          />
          <SwitchField
            label="Only passengers of my gender"
            description="A hard filter: nobody else will find this ride."
            checked={values.preferences.gender_only}
            onChange={(checked) => setPreference('gender_only', checked)}
          />
        </div>
        {genderOnlyWithoutGender ? (
          <p role="alert" className="mt-2 text-sm font-medium text-alert">
            Your profile has no gender set, so this filter would hide the ride from everyone. Set it
            on your profile or turn this off.
          </p>
        ) : null}
      </section>

      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="quiet" disabled={pending} onClick={onCancel}>
            Discard
          </Button>
        ) : null}
      </div>
    </form>
  )
}
